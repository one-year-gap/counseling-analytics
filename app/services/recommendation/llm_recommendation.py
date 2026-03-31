"""임베딩·벡터 후보·LLM 호출로 RecommendationResponse 생성."""

from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.schemas.recommendation import RecommendedProductItem, RecommendationResponse, Segment
from app.services.persona_recommendation_prompts import (
    build_user_prompt,
    format_products,
    get_persona_style_prompt,
    get_segment_system_prompt,
)
from app.services.retrieval_query_builder import build_retrieval_query_text

from .constants import (
    CHURN_MAX_PRICE_RATIO,
    DEFAULT_PRODUCT_REASON_TEXT,
    DEFAULT_RETRIEVAL_QUERY,
    FETCH_DEFAULT_PRODUCTS_SQL,
    FETCH_PRODUCTS_FULL_SQL,
    FALLBACK_VECTOR_SUMMARY,
    MAX_PRODUCTS_PER_TYPE,
    NO_CANDIDATE_MESSAGE,
    NO_MATCHED_MESSAGE,
    RETRIEVAL_CANDIDATES_K,
    RETRIEVAL_PER_TYPE_K,
    SEARCH_SIMILAR_SQL,
    SEARCH_SIMILAR_WITH_TYPE_BOOST_SQL,
)
from .retrieval import get_subscription_max_price_by_type, retrieve_product_ids_per_main_type_window
from .utils import (
    check_and_update_product_type_count,
    diversify_products_by_type,
    exclude_ids_from_context,
    is_age_allowed_for_tags,
    normalize_embedding_for_db,
    normalize_tags,
    reorder_by_data_usage_pattern,
    segment_enum,
    utc_now_iso,
)
from .weights import compute_product_type_weights, product_type_boost_from_weights

logger = logging.getLogger(__name__)


async def generate_recommendation_reasons(
    client: AsyncOpenAI,
    model: str,
    product_summaries: list[str],
) -> list[str]:
    if not product_summaries:
        return []
    lines = [f"{i+1}. {s}" for i, s in enumerate(product_summaries)]
    product_list = "\n".join(lines)
    system_fallback = (
        "당신은 통신사 개인화 추천 AI입니다. 각 상품 추천 이유를 2~3문장으로 구체적으로 작성하세요. "
        "가격·혜택·태그·대상 고객 관점을 포함하면 좋습니다."
    )
    prompt = f"""아래 상품들을 고객에게 추천했습니다. 각 상품을 왜 추천했는지 2~3문장으로 구체적으로 설명해주세요.
상품 목록:
{product_list}

응답은 반드시 JSON만 주세요. 예시: {{"reasons": ["이유1(2~3문장)", "이유2(2~3문장)", "이유3(2~3문장)"]}}
"""
    try:
        logger.info(
            "OpenAI Chat 호출 직전 (_generate_recommendation_reasons): model=%s product_count=%d prompt_len=%d",
            model,
            len(product_summaries),
            len(prompt),
        )
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_fallback},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        content = (resp.choices[0].message.content or "").strip()
        logger.info(
            "OpenAI Chat 성공 (_generate_recommendation_reasons): model=%s response_len=%d",
            model,
            len(content),
        )
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            data = json.loads(m.group())
            reasons = data.get("reasons") or []
            if isinstance(reasons, list):
                processed = [str(r).strip() or "고객님께 적합한 상품입니다." for r in reasons]
                if len(processed) < len(product_summaries):
                    processed.extend(
                        ["고객님께 적합한 상품입니다."] * (len(product_summaries) - len(processed))
                    )
                return processed[: len(product_summaries)]
    except Exception as e:
        if isinstance(e, (json.JSONDecodeError, KeyError, IndexError)):
            logger.warning(
                "LLM 추천 이유 파싱 실패, 기본 문구 사용: model=%s error_type=%s error=%s",
                model,
                type(e).__name__,
                e,
                exc_info=True,
            )
        else:
            logger.warning(
                "OpenAI Chat API 실패 (_generate_recommendation_reasons): model=%s error_type=%s error=%s",
                model,
                type(e).__name__,
                e,
                exc_info=True,
            )
    return ["고객님께 적합한 상품입니다."] * len(product_summaries)


async def run_recommendation_with_context(
    session: AsyncSession,
    member_id: int,
    ctx: dict,
    settings: object,
    client: AsyncOpenAI,
) -> RecommendationResponse | None:
    top_k = getattr(settings, "recommend_top_k", 3)
    query_text = build_retrieval_query_text(ctx)
    exclude_ids = exclude_ids_from_context(ctx)
    emb_model = getattr(settings, "openai_embedding_model", "")
    logger.info(
        "OpenAI 임베딩 호출 직전: member_id=%s model=%s query_text_len=%d query_text_preview=%s",
        member_id,
        emb_model,
        len(query_text or ""),
        (query_text or "")[:80] + ("..." if len(query_text or "") > 80 else ""),
    )

    type_caps = (
        await get_subscription_max_price_by_type(session, ctx)
        if (ctx.get("segment") or "").strip().upper() == "CHURN_RISK"
        else {}
    )

    try:
        emb_resp = await client.embeddings.create(
            model=settings.openai_embedding_model,
            input=query_text,
        )
        query_vec = emb_resp.data[0].embedding
        logger.info(
            "OpenAI 임베딩 성공: member_id=%s model=%s dimension=%d",
            member_id,
            emb_model,
            len(query_vec) if query_vec else 0,
        )
    except Exception as e:
        logger.warning(
            "OpenAI 임베딩 실패 (ctx 경로): member_id=%s model=%s error_type=%s error=%s",
            member_id,
            emb_model,
            type(e).__name__,
            e,
            exc_info=True,
        )
        return None
    query_vec = normalize_embedding_for_db(query_vec)
    if query_vec is None:
        return None

    product_type_weights = compute_product_type_weights(ctx)
    boost_type1, boost1, boost_type2, boost2 = product_type_boost_from_weights(product_type_weights)
    use_type_boost = boost1 > 0 or boost2 > 0

    product_ids = await retrieve_product_ids_per_main_type_window(
        session,
        query_vec,
        exclude_ids,
        RETRIEVAL_PER_TYPE_K,
    )
    seen: set[int] = set(product_ids)

    if len(product_ids) < RETRIEVAL_CANDIDATES_K:
        if use_type_boost:
            result = await session.execute(
                SEARCH_SIMILAR_WITH_TYPE_BOOST_SQL,
                {
                    "query_vec": query_vec,
                    "exclude_ids": exclude_ids,
                    "k": RETRIEVAL_CANDIDATES_K,
                    "boost_type1": boost_type1,
                    "boost1": boost1,
                    "boost_type2": boost_type2,
                    "boost2": boost2,
                },
            )
        else:
            result = await session.execute(
                SEARCH_SIMILAR_SQL,
                {
                    "query_vec": query_vec,
                    "exclude_ids": exclude_ids,
                    "k": RETRIEVAL_CANDIDATES_K,
                },
            )
        for row in result.fetchall():
            pid = row[0]
            if pid in seen:
                continue
            product_ids.append(pid)
            seen.add(pid)
            if len(product_ids) >= RETRIEVAL_CANDIDATES_K:
                break

    if not product_ids:
        return RecommendationResponse(
            segment=segment_enum(ctx.get("segment")),
            cached_llm_recommendation="추천할 수 있는 상품이 없습니다.",
            recommended_products=[],
            source="LIVE",
            updated_at=utc_now_iso(),
        )

    full_result = await session.execute(FETCH_PRODUCTS_FULL_SQL, {"ids": product_ids})
    id_to_row = {}
    for row in full_result.mappings():
        r = dict(row)
        id_to_row[r["product_id"]] = r
    products_ordered = [id_to_row[pid] for pid in product_ids if pid in id_to_row]

    type_counts: dict[str, int] = {}
    for p in products_ordered:
        ptype = (p.get("product_type") or "").strip().upper()
        type_counts[ptype] = type_counts.get(ptype, 0) + 1
    logger.info(
        "recommendation: ctx retrieval 완료 member_id=%s 후보=%d type_dist=%s",
        member_id,
        len(products_ordered),
        type_counts,
    )

    if type_caps:
        filtered = []
        for p in products_ordered:
            ptype = (p.get("product_type") or "").strip()
            sale = int(p.get("sale_price") or p.get("price") or 0)
            if ptype not in type_caps:
                filtered.append(p)
            elif sale <= int(type_caps[ptype] * CHURN_MAX_PRICE_RATIO):
                filtered.append(p)
        products_ordered = filtered

    products_ordered = reorder_by_data_usage_pattern(
        products_ordered,
        ctx.get("data_usage_pattern"),
    )

    base_candidates = [p for p in products_ordered if is_age_allowed_for_tags(ctx, p)]

    if not base_candidates:
        return RecommendationResponse(
            segment=segment_enum(ctx.get("segment")),
            cached_llm_recommendation=NO_MATCHED_MESSAGE,
            recommended_products=[],
            source="LIVE",
            updated_at=utc_now_iso(),
        )

    primary = diversify_products_by_type(
        base_candidates,
        max_per_type=MAX_PRODUCTS_PER_TYPE,
        max_total=5,
    )

    if len(primary) >= top_k:
        products_ordered = primary[:top_k]
    else:
        used_ids = {p["product_id"] for p in primary}
        extra: list[dict] = []
        for p in base_candidates:
            pid = p.get("product_id")
            if pid in used_ids:
                continue
            extra.append(p)
            used_ids.add(pid)
            if len(primary) + len(extra) >= top_k:
                break
        products_ordered = (primary + extra)[:top_k]

    for p in products_ordered:
        p["product_name"] = p.get("name") or ""
        p["product_price"] = int(p.get("price") or 0)
        p["sale_price"] = int(p.get("sale_price") or p.get("price") or 0)
        p["tags"] = normalize_tags(p.get("tags"))

    products_text = format_products(products_ordered)
    segment = (ctx.get("segment") or "NORMAL").strip()
    persona_code = ctx.get("persona_code")
    system_prompt = get_segment_system_prompt(segment) + "\n\n" + get_persona_style_prompt(persona_code)
    user_prompt = build_user_prompt(ctx, products_text)

    json_instruction = (
        "응답은 반드시 아래 JSON 형식만 출력해 줄 거예요. 다른 말은 쓰지 말고 JSON만 보내 주세요.\n"
        "{"
        "\"cached_llm_recommendation\": \"전체 추천을 대표하는 전반적인 마케팅 문구를 2~4문장으로 써 줄 거예요. "
        "고객의 세그먼트, 페르소나, 최근 상담 및 이용 패턴을 부드럽게 요약해 주고, 이번에 제안하는 상품 조합의 핵심 혜택과 가치를 자연스러운 카피 톤으로 설명해 주세요.\", "
        "\"recommended_products\": ["
        "{"
        "\"product_id\": 숫자, "
        "\"reason\": \"각 상품별로 2~3문장으로 써 줄 거예요. "
        "반드시 (1) 현재 고객이 이용 중인 요금제/상품/지출 수준이나 사용 패턴과 비교해서, "
        "가격이나 혜택 측면에서 뭐가 어떻게 더 좋아지는지 한 문장 이상으로 구체적으로 설명해 주세요. "
        "(2) 고객의 데이터 사용 패턴, 가족 구성, 최근 상담 내용, 최근 조회 태그, segment, persona 등 컨텍스트 중에서 최소 한 가지는 문장 안에 꼭 넣어 줄 거예요. "
        "단순히 '다양한 혜택을 제공합니다', '고객님께 적합한 상품입니다', '안정성과 편의를 모두 고려한 선택입니다'처럼 누구에게나 쓸 수 있는 추상적인 카탈로그 문구만 쓰는 건 피해 주세요. "
        "상품 스펙(속도, 채널 수, 기본 기능 등)을 다시 나열하기보다는, 지금 고객 입장에서 무엇이 어떻게 달라지는지를 중심으로 reason을 써 주면 좋아요.\""
        "}, ..."
        "]"
        "}"
    )
    chat_model = getattr(settings, "openai_chat_model", "")
    system_len = len(system_prompt + "\n\n" + json_instruction)
    user_len = len(user_prompt or "")
    logger.info(
        "OpenAI Chat 호출 직전 (ctx 경로): member_id=%s model=%s system_len=%d user_len=%d products=%d",
        member_id,
        chat_model,
        system_len,
        user_len,
        len(products_ordered[:top_k]),
    )
    try:
        resp = await client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system_prompt + "\n\n" + json_instruction},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        content = (resp.choices[0].message.content or "").strip()
        logger.info(
            "OpenAI Chat 성공 (ctx 경로): member_id=%s model=%s response_len=%d",
            member_id,
            chat_model,
            len(content),
        )
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            raise ValueError("JSON not found in response")
        data = json.loads(m.group())
        cached = (data.get("cached_llm_recommendation") or "").strip()
        if not cached:
            cached = "고객님의 이용 패턴과 관심사를 반영한 개인화 추천입니다."
        raw_list = data.get("recommended_products") or []
    except Exception as e:
        if isinstance(e, (json.JSONDecodeError, KeyError, ValueError)):
            logger.warning(
                "LLM JSON 파싱 실패 (ctx 경로), 폴백 사용: member_id=%s error_type=%s error=%s",
                member_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
        else:
            logger.warning(
                "OpenAI Chat API 호출 실패 (ctx 경로): member_id=%s model=%s error_type=%s error=%s",
                member_id,
                chat_model,
                type(e).__name__,
                e,
                exc_info=True,
            )
        raw_list = [
            {"product_id": p["product_id"], "reason": "고객님께 가장 적합한 상품을 추천드립니다!"}
            for p in products_ordered[:top_k]
        ]
        cached = "고객님의 이용 패턴과 관심사를 반영한 요금제·부가서비스 추천입니다."

    recommended_products: list[RecommendedProductItem] = []
    used_ids: set[int] = set()
    type_counts_llm: dict[str, int] = {}

    for item in raw_list:
        pid = item.get("product_id")
        reason = (item.get("reason") or "").strip() or "고객님께 가장 적합한 상품을 추천드립니다!"
        if pid not in id_to_row:
            continue
        p = id_to_row[pid]
        if not check_and_update_product_type_count(p, type_counts_llm, MAX_PRODUCTS_PER_TYPE):
            continue
        ptype = (p.get("product_type") or "").strip()
        tags = normalize_tags(p.get("tags"))
        rank = len(recommended_products) + 1
        if rank > top_k:
            break
        recommended_products.append(
            RecommendedProductItem(
                rank=rank,
                product_id=p["product_id"],
                product_name=(p.get("name") or "").strip(),
                product_type=ptype,
                product_price=int(p.get("price") or 0),
                sale_price=int(p.get("sale_price") or p.get("price") or 0),
                tags=tags,
                llm_reason=reason,
            )
        )
        used_ids.add(p["product_id"])

    if len(recommended_products) < top_k:
        for p in products_ordered:
            pid = p.get("product_id")
            if pid in used_ids:
                continue
            if not check_and_update_product_type_count(p, type_counts_llm, MAX_PRODUCTS_PER_TYPE):
                continue
            ptype = (p.get("product_type") or "").strip()
            tags = normalize_tags(p.get("tags"))
            rank = len(recommended_products) + 1
            if rank > top_k:
                break
            recommended_products.append(
                RecommendedProductItem(
                    rank=rank,
                    product_id=pid,
                    product_name=(p.get("name") or "").strip(),
                    product_type=ptype,
                    product_price=int(p.get("price") or 0),
                    sale_price=int(p.get("sale_price") or p.get("price") or 0),
                    tags=tags,
                    llm_reason="고객님께 가장 적합한 상품을 추천드립니다!",
                )
            )
            used_ids.add(pid)

    return RecommendationResponse(
        segment=segment_enum(ctx.get("segment")),
        cached_llm_recommendation=cached,
        recommended_products=recommended_products,
        source="LIVE",
        updated_at=utc_now_iso(),
    )


async def run_fallback_recommendation(
    client: AsyncOpenAI,
    settings: object,
    top_k: int,
) -> RecommendationResponse:
    logger.info("recommendation: 폴백 시작 (고정 쿼리 벡터 검색) top_k=%s", top_k)
    if SessionLocal is None:
        return RecommendationResponse(
            segment=Segment.normal,
            cached_llm_recommendation="DB 미설정으로 추천을 생성할 수 없습니다.",
            recommended_products=[],
            source="LIVE",
            updated_at=utc_now_iso(),
        )
    emb_model = getattr(settings, "openai_embedding_model", "")
    async with SessionLocal() as fallback_session:
        try:
            logger.info(
                "OpenAI 임베딩 호출 직전 (폴백): model=%s input_preview=%s",
                emb_model,
                (DEFAULT_RETRIEVAL_QUERY or "")[:60] + ("..." if len(DEFAULT_RETRIEVAL_QUERY or "") > 60 else ""),
            )
            emb_resp = await client.embeddings.create(
                model=settings.openai_embedding_model,
                input=DEFAULT_RETRIEVAL_QUERY,
            )
            query_vec = emb_resp.data[0].embedding
            logger.info(
                "OpenAI 임베딩 성공 (폴백): model=%s dimension=%d",
                emb_model,
                len(query_vec) if query_vec else 0,
            )
        except Exception as e:
            logger.warning(
                "OpenAI 임베딩 실패 (폴백, 기본 상품으로 대체): model=%s error_type=%s error=%s",
                emb_model,
                type(e).__name__,
                e,
                exc_info=True,
            )
            default_result = await fallback_session.execute(
                FETCH_DEFAULT_PRODUCTS_SQL,
                {"k": top_k},
            )
            rows = list(default_result.mappings())
            if not rows:
                return RecommendationResponse(
                    segment=Segment.normal,
                    cached_llm_recommendation=NO_CANDIDATE_MESSAGE,
                    recommended_products=[],
                    source="LIVE",
                    updated_at=utc_now_iso(),
                )
            recommended_products_fb: list[RecommendedProductItem] = []
            type_counts_fb: dict[str, int] = {}
            for row in rows:
                p = dict(row)
                if not check_and_update_product_type_count(p, type_counts_fb, MAX_PRODUCTS_PER_TYPE):
                    continue
                tags = normalize_tags(p.get("tags"))
                rank = len(recommended_products_fb) + 1
                if rank > top_k:
                    break
                recommended_products_fb.append(
                    RecommendedProductItem(
                        rank=rank,
                        product_id=p["product_id"],
                        product_name=(p.get("name") or "").strip(),
                        product_type=(p.get("product_type") or "").strip(),
                        product_price=int(p.get("price") or 0),
                        sale_price=int(p.get("sale_price") or p.get("price") or 0),
                        tags=tags,
                        llm_reason=DEFAULT_PRODUCT_REASON_TEXT,
                    )
                )
            return RecommendationResponse(
                segment=Segment.normal,
                cached_llm_recommendation="아직 추천을 생성할만한 정보가 없어요. 대신 이 상품은 어떠세요?",
                recommended_products=recommended_products_fb,
                source="LIVE",
                updated_at=utc_now_iso(),
            )
        query_vec = normalize_embedding_for_db(query_vec)
        if query_vec is None:
            return RecommendationResponse(
                segment=Segment.normal,
                cached_llm_recommendation="임베딩 차원이 DB(VECTOR(1536))와 맞지 않습니다. openai_embedding_model과 상품 인덱싱 모델을 동일하게 설정하세요.",
                recommended_products=[],
                source="LIVE",
                updated_at=utc_now_iso(),
            )

        product_ids = await retrieve_product_ids_per_main_type_window(
            fallback_session,
            query_vec,
            [0],
            RETRIEVAL_PER_TYPE_K,
        )
        seen: set[int] = set(product_ids)

        if len(product_ids) < RETRIEVAL_CANDIDATES_K:
            result = await fallback_session.execute(
                SEARCH_SIMILAR_SQL,
                {
                    "query_vec": query_vec,
                    "exclude_ids": [0],
                    "k": RETRIEVAL_CANDIDATES_K,
                },
            )
            for row in result.fetchall():
                pid = row[0]
                if pid in seen:
                    continue
                product_ids.append(pid)
                seen.add(pid)
                if len(product_ids) >= RETRIEVAL_CANDIDATES_K:
                    break
        logger.info("recommendation: 폴백 벡터 검색 완료 product_ids=%s", product_ids[:10] if len(product_ids) > 10 else product_ids)
        if not product_ids:
            return RecommendationResponse(
                segment=Segment.normal,
                cached_llm_recommendation="추천할 수 있는 상품이 없습니다.",
                recommended_products=[],
                source="LIVE",
                updated_at=utc_now_iso(),
            )

        full_result = await fallback_session.execute(FETCH_PRODUCTS_FULL_SQL, {"ids": product_ids})
        id_to_row = {}
        for row in full_result.mappings():
            r = dict(row)
            id_to_row[r["product_id"]] = r
        products_ordered = [id_to_row[pid] for pid in product_ids if pid in id_to_row]

        fb_type_counts: dict[str, int] = {}
        for p in products_ordered:
            ptype = (p.get("product_type") or "").strip().upper()
            fb_type_counts[ptype] = fb_type_counts.get(ptype, 0) + 1
        logger.info(
            "recommendation: fallback retrieval 완료 후보=%d type_dist=%s",
            len(products_ordered),
            fb_type_counts,
        )

        if not products_ordered:
            return RecommendationResponse(
                segment=Segment.normal,
                cached_llm_recommendation="추천 상품 정보를 불러오지 못했습니다.",
                recommended_products=[],
                source="LIVE",
                updated_at=utc_now_iso(),
            )

        max_total = min(top_k, 5)
        products_ordered = diversify_products_by_type(
            products_ordered,
            max_per_type=MAX_PRODUCTS_PER_TYPE,
            max_total=max_total,
        )

        summaries = [
            f"{p.get('name') or ''} (product_id={p.get('product_id')})"
            for p in products_ordered
        ]
        logger.info("recommendation: 폴백 LLM reason 생성 요청 상품=%d", len(summaries))
        reasons = await generate_recommendation_reasons(
            client,
            settings.openai_chat_model,
            summaries,
        )
        recommended_products_out: list[RecommendedProductItem] = []
        type_counts_out: dict[str, int] = {}
        for p in products_ordered:
            if not check_and_update_product_type_count(p, type_counts_out, MAX_PRODUCTS_PER_TYPE):
                continue
            ptype = (p.get("product_type") or "").strip()
            tags = normalize_tags(p.get("tags"))
            rank = len(recommended_products_out) + 1
            if rank > top_k:
                break
            recommended_products_out.append(
                RecommendedProductItem(
                    rank=rank,
                    product_id=p["product_id"],
                    product_name=(p.get("name") or "").strip(),
                    product_type=ptype,
                    product_price=int(p.get("price") or 0),
                    sale_price=int(p.get("sale_price") or p.get("price") or 0),
                    tags=tags,
                    llm_reason=reasons[rank - 1] if rank - 1 < len(reasons) else DEFAULT_PRODUCT_REASON_TEXT,
                )
            )
        return RecommendationResponse(
            segment=Segment.normal,
            cached_llm_recommendation=FALLBACK_VECTOR_SUMMARY,
            recommended_products=recommended_products_out,
            source="LIVE",
            updated_at=utc_now_iso(),
        )
