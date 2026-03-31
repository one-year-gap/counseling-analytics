import logging
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.schemas.recommendation import RecommendationRequest
from app.services.recommendation_service import run_recommendation_and_publish_to_kafka

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/recommendations", status_code=202)
async def post_recommendations(
    body: RecommendationRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """
    202 Accepted 즉시 반환. 백그라운드에서 추천 생성 후 Kafka recommendation-topic 발행.
    Spring이 Kafka consume → persona_recommendation 적재 → CompletableFuture.complete(결과).
    """
    _ = session
    t0 = time.monotonic()
    trace_id = (
        (request.headers.get("x-trace-id") or "").strip()
        or uuid.uuid4().hex[:12]
    )
    member_id = body.member_id

    logger.info("[REC][trace_id=%s][member_id=%s] fastapi_start", trace_id, member_id)
    background_tasks.add_task(run_recommendation_and_publish_to_kafka, member_id, trace_id)
    total_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "[REC][trace_id=%s][member_id=%s] fastapi_end total_ms=%s",
        trace_id,
        member_id,
        total_ms,
    )
    return Response(status_code=202, content=None)
