"""추천 오케스트레이션·공개 진입점."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.infra.openai.app_client import get_openai_client
from app.schemas.recommendation import RecommendationResponse, Segment

from .context_loader import load_member_llm_context
from .kafka_publish import publish_recommendation_to_kafka
from .llm_recommendation import run_fallback_recommendation, run_recommendation_with_context
from .utils import utc_now_iso

logger = logging.getLogger(__name__)


class RecommendationService:
    def __init__(self, settings: object, client: AsyncOpenAI) -> None:
        self.settings = settings
        self.client = client

    async def recommend_for_member(self, member_id: int) -> RecommendationResponse:
        logger.info("recommendation: 요청 시작 member_id=%s", member_id)
        top_k = getattr(self.settings, "recommend_top_k", 3)

        if SessionLocal is None:
            logger.warning("recommendation: DB 미설정, 빈 응답 반환 member_id=%s", member_id)
            return RecommendationResponse(
                segment=Segment.normal,
                cached_llm_recommendation="DB가 설정되지 않았습니다.",
                recommended_products=[],
                source="LIVE",
                updated_at=utc_now_iso(),
            )

        async with SessionLocal() as worker_session:
            ctx: dict | None = await load_member_llm_context(worker_session, member_id)

            if ctx:
                logger.info(
                    "recommendation: member_llm_context 사용 (member_id=%s, segment=%s, persona=%s)",
                    member_id,
                    (ctx.get("segment") or "").strip(),
                    (ctx.get("persona_code") or "").strip(),
                )
                try:
                    resp = await run_recommendation_with_context(
                        session=worker_session,
                        member_id=member_id,
                        ctx=ctx,
                        settings=self.settings,
                        client=self.client,
                    )
                    if resp is not None:
                        logger.info(
                            "recommendation: ctx 경로 완료 member_id=%s segment=%s products=%s",
                            member_id,
                            resp.segment.value,
                            len(resp.recommended_products),
                        )
                        return resp
                except Exception as e:
                    logger.info(
                        "recommendation: ctx 기반 추천 실패 → 폴백 (member_id=%s, error=%s)",
                        member_id,
                        e,
                    )
                    try:
                        await worker_session.rollback()
                    except Exception:
                        pass  # best-effort rollback after pipeline failure

        logger.info(
            "recommendation: 폴백 경로 진입 (member_llm_context 없음 또는 ctx 추천 실패, member_id=%s)",
            member_id,
        )
        resp = await run_fallback_recommendation(
            client=self.client,
            settings=self.settings,
            top_k=top_k,
        )
        logger.info(
            "recommendation: 폴백 경로 완료 member_id=%s segment=%s products=%s",
            member_id,
            resp.segment.value,
            len(resp.recommended_products),
        )
        return resp


async def get_recommendation(
    session: AsyncSession | None,
    member_id: int,
) -> RecommendationResponse:
    _ = session
    settings = get_settings()
    api_key = getattr(settings, "openai_api_key", "") or ""
    has_key = bool(api_key and api_key.strip())
    logger.info(
        "get_recommendation: 진입 member_id=%s openai_api_key_set=%s openai_embedding_model=%s openai_chat_model=%s",
        member_id,
        has_key,
        getattr(settings, "openai_embedding_model", ""),
        getattr(settings, "openai_chat_model", ""),
    )
    if not has_key:
        logger.error(
            "get_recommendation: OPENAI_API_KEY 미설정. .env 또는 환경변수 OPENAI_API_KEY 확인 필요. member_id=%s",
            member_id,
        )
        return RecommendationResponse(
            segment=Segment.normal,
            cached_llm_recommendation="[설정 오류] OpenAI API 키가 설정되지 않았습니다.",
            recommended_products=[],
            source="LIVE",
            updated_at=utc_now_iso(),
        )

    client = get_openai_client()
    if client is None:
        client = AsyncOpenAI(api_key=api_key)
    service = RecommendationService(settings=settings, client=client)
    try:
        return await service.recommend_for_member(member_id)
    except Exception as e:
        logger.exception(
            "get_recommendation: OpenAI 또는 추천 파이프라인 예외 member_id=%s error_type=%s error=%s",
            member_id,
            type(e).__name__,
            e,
        )
        return RecommendationResponse(
            segment=Segment.normal,
            cached_llm_recommendation="[일시 오류] 추천을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.(openai)",
            recommended_products=[],
            source="LIVE",
            updated_at=utc_now_iso(),
        )


async def run_recommendation_and_publish_to_kafka(member_id: int) -> None:
    try:
        resp = await get_recommendation(session=None, member_id=member_id)
        await publish_recommendation_to_kafka(member_id, resp)
    except Exception as e:
        logger.error("recommendation: 백그라운드 추천/Kafka 실패 member_id=%s: %s", member_id, e, exc_info=True)
