"""추천 결과 Kafka 발행."""

from __future__ import annotations

import json
import logging

try:
    from aiokafka import AIOKafkaProducer
except Exception:  # pragma: no cover
    AIOKafkaProducer = None  # type: ignore[assignment]

from app.core.config import get_settings
from app.infra.kafka.client_options import build_kafka_client_options
from app.infra.kafka.recommendation_producer import get_recommendation_kafka_producer
from app.schemas.recommendation import RecommendationResponse

logger = logging.getLogger(__name__)


async def publish_recommendation_to_kafka(
    member_id: int,
    response: RecommendationResponse,
    trace_id: str | None = None,
) -> None:
    settings = get_settings()
    topic = getattr(settings, "kafka_recommendation_topic", "recommendation")
    bootstrap = getattr(settings, "kafka_bootstrap_servers", "").strip()
    if AIOKafkaProducer is None:
        logger.warning("recommendation: aiokafka 미설치, Kafka 발행 스킵 member_id=%s", member_id)
        return
    if not bootstrap:
        logger.warning("recommendation: Kafka 미설정, 발행 스킵 member_id=%s", member_id)
        return
    tid = (trace_id or "").strip()
    payload = {"traceId": tid, "memberId": member_id, **response.model_dump(by_alias=True)}

    shared = get_recommendation_kafka_producer()
    owned = False
    producer = shared
    if producer is None:
        producer = AIOKafkaProducer(
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            **build_kafka_client_options(settings),
        )
        await producer.start()
        owned = True
    try:
        await producer.send_and_wait(topic, value=payload, key=str(member_id).encode("utf-8"))
        logger.info("recommendation: Kafka 발행 완료 member_id=%s topic=%s", member_id, topic)
    except Exception as e:
        logger.error("recommendation: Kafka 발행 실패 member_id=%s: %s", member_id, e, exc_info=True)
    finally:
        if owned:
            await producer.stop()
