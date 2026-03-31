"""member_llm_context 로딩."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from .constants import FETCH_MEMBER_LLM_CONTEXT_SQL

logger = logging.getLogger(__name__)


async def load_member_llm_context(session: AsyncSession, member_id: int) -> dict | None:
    try:
        ctx_result = await session.execute(
            FETCH_MEMBER_LLM_CONTEXT_SQL,
            {"member_id": member_id},
        )
        row = ctx_result.fetchone()
        if row is None:
            logger.info(
                "recommendation: member_llm_context 행 없음 (member_id=%s). 테이블은 있으나 해당 회원 데이터 없음 → 폴백",
                member_id,
            )
            return None
        return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    except Exception as e:
        logger.info(
            "recommendation: member_llm_context 조회 실패 → 폴백 예정 (member_id=%s, error=%s)",
            member_id,
            e,
        )
        try:
            await session.rollback()
        except Exception:
            pass  # best-effort: 이미 닫힌 세션 등에서 rollback 실패 가능
        return None
