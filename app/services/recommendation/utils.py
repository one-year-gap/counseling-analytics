"""추천 파이프라인 순수 유틸(태그·연령·정렬·시간 등)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.schemas.recommendation import Segment

from .constants import EMBEDDING_DIMENSION, UNLIMITED_DATA_TAG_MARKER

logger = logging.getLogger(__name__)


def normalize_embedding_for_db(embedding: list[float]) -> list[float] | None:
    if len(embedding) == EMBEDDING_DIMENSION:
        return embedding
    if len(embedding) > EMBEDDING_DIMENSION:
        logger.warning(
            "임베딩 차원 초과: %d (기대 %d). 앞 %d개만 사용. product.embedding_vector와 동일 모델(openai_embedding_model) 사용 권장.",
            len(embedding),
            EMBEDDING_DIMENSION,
            EMBEDDING_DIMENSION,
        )
        return embedding[:EMBEDDING_DIMENSION]
    logger.error(
        "임베딩 차원 부족: %d (기대 %d). openai_embedding_model이 text-embedding-3-small인지, product 인덱싱과 동일 모델인지 확인.",
        len(embedding),
        EMBEDDING_DIMENSION,
    )
    return None


def age_from_ctx(ctx: dict) -> int | None:
    raw = (ctx.get("age_group") or "").strip()
    num_str = "".join(ch for ch in raw if ch.isdigit())
    if not num_str:
        return None
    try:
        return int(num_str)
    except ValueError:
        return None


def is_age_allowed_for_tags(ctx: dict, product: dict) -> bool:
    age = age_from_ctx(ctx)
    if age is None:
        return True

    tags = normalize_tags(product.get("tags"))

    has_kids_tags = any("키즈" in t or "자녀보호" in t for t in tags)
    has_teen_tag = any("청소년" in t for t in tags)
    has_young20_tag = any("20대청년" in t for t in tags)
    has_senior_tags = any("시니어" in t or "복지혜택" in t for t in tags)
    has_soldier_tag = any("현역병사" in t for t in tags)

    if not (has_kids_tags or has_teen_tag or has_young20_tag or has_senior_tags or has_soldier_tag):
        return True

    if has_kids_tags and age < 30:
        return False
    if has_teen_tag and age != 10:
        return False
    if has_young20_tag and age != 20:
        return False
    if has_soldier_tag and age != 20:
        return False
    if has_senior_tags and age < 50:
        return False

    return True


def check_and_update_product_type_count(
    product: dict,
    type_counts: dict[str, int],
    max_per_type: int,
) -> bool:
    ptype = (product.get("product_type") or "").strip()
    tcode = ptype.upper()
    if not tcode:
        return True
    current = type_counts.get(tcode, 0)
    if current >= max_per_type:
        return False
    type_counts[tcode] = current + 1
    return True


def embedding_to_vector_str(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def has_unlimited_data_tag(tags: list[str] | None) -> bool:
    if not tags:
        return False
    return any(UNLIMITED_DATA_TAG_MARKER in (t or "") for t in tags)


def reorder_by_data_usage_pattern(
    products: list[dict],
    data_usage_pattern: str | None,
) -> list[dict]:
    if not products:
        return products
    pattern = (data_usage_pattern or "").strip().upper()
    if pattern != "OVER" and pattern != "UNDER":
        return products

    def sort_key(p: dict) -> tuple:
        tags = normalize_tags(p.get("tags"))
        has_unlimited = has_unlimited_data_tag(tags)
        data_amount = p.get("data_amount")
        if data_amount is not None:
            try:
                amount = int(data_amount)
            except (TypeError, ValueError):
                amount = 0
        else:
            amount = None

        if pattern == "OVER":
            rank = 0 if has_unlimited else 1
            rev_amount = -(amount if amount is not None and amount > 0 else 0)
            return (rank, rev_amount)
        rank = 1 if has_unlimited else 0
        amount_val = amount if amount is not None and amount >= 0 else 999999
        return (rank, amount_val)

    return sorted(products, key=sort_key)


def diversify_products_by_type(
    products: list[dict],
    max_per_type: int = 1,
    max_total: int | None = None,
) -> list[dict]:
    if not products:
        return products

    type_counts: dict[str, int] = {}
    diversified: list[dict] = []

    for p in products:
        ptype = (p.get("product_type") or "").strip()
        key = ptype.upper()
        current = type_counts.get(key, 0)
        if max_per_type is not None and current >= max_per_type:
            continue

        diversified.append(p)
        type_counts[key] = current + 1

        if max_total is not None and len(diversified) >= max_total:
            break

    return diversified or products


def normalize_tags(tags: list | str | None) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(t).strip() for t in tags if str(t).strip()]
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            return normalize_tags(parsed)
        except json.JSONDecodeError:
            return [tags.strip()] if tags.strip() else []
    return []


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def exclude_ids_from_context(ctx: dict) -> list[int]:
    raw = ctx.get("current_subscriptions")
    if not raw:
        return [0]
    if isinstance(raw, list):
        ids = []
        for x in raw:
            if isinstance(x, dict) and "product_id" in x:
                ids.append(int(x["product_id"]))
            elif isinstance(x, (int, float)):
                ids.append(int(x))
        return ids if ids else [0]
    if isinstance(raw, str):
        try:
            arr = json.loads(raw)
            return exclude_ids_from_context({"current_subscriptions": arr})
        except json.JSONDecodeError:
            pass
    return [0]


def segment_enum(segment: str | None) -> Segment:
    if not segment:
        return Segment.normal
    s = (segment or "").strip().upper()
    if s == "CHURN_RISK":
        return Segment.churn_risk
    if s == "UPSELL":
        return Segment.upsell
    return Segment.normal


def segment_key_from_ctx(ctx: dict) -> str:
    seg = (ctx.get("segment") or "NORMAL").strip().upper()
    from .constants import SEGMENT_WEIGHT_CONFIG

    if seg not in SEGMENT_WEIGHT_CONFIG:
        seg = "NORMAL"
    return seg


def infer_product_types_from_tag(tag: str) -> list[str]:
    if not tag:
        return []
    t = str(tag).strip().upper()
    related: list[str] = []
    if "OTT" in t or "NETFLIX" in t or "DISNEY" in t or "WATCH" in t:
        related.extend(["INTERNET", "IPTV"])
    if "FAMILY" in t or "가족" in t:
        related.extend(["INTERNET", "MOBILE_PLAN"])
    if "SECURITY" in t or "보안" in t or "안심" in t:
        related.append("SECURITY_ADDON")
    if "KIDS" in t or "자녀" in t:
        related.append("KIDS_ADDON")
    return sorted({x for x in related if x})
