"""추천 결과 발행용 Kafka producer. 앱 lifespan 동안 1개 인스턴스를 재사용한다."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import Settings, get_settings
from app.infra.kafka.client_options import build_kafka_client_options

logger = logging.getLogger(__name__)

_producer: Any = None


async def start_recommendation_kafka_producer(settings: Settings | None = None) -> None:
    """bootstrap이 설정된 경우에만 producer를 생성·시작한다. 실패 시 로그만 남기고 계속 기동."""
    global _producer
    if _producer is not None:
        return
    try:
        from aiokafka import AIOKafkaProducer
    except ImportError:
        logger.info("aiokafka 미설치, 추천용 Kafka producer 생략")
        return

    s = settings or get_settings()
    bootstrap = (s.kafka_bootstrap_servers or "").strip()
    if not bootstrap:
        logger.info("kafka_bootstrap_servers 비어 있음, 추천용 Kafka producer 생략")
        return

    producer = AIOKafkaProducer(
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        **build_kafka_client_options(s),
    )
    try:
        await producer.start()
    except Exception:
        logger.exception("추천용 Kafka producer 시작 실패 (bootstrap=%s)", bootstrap[:80])
        return
    _producer = producer
    logger.info("추천용 Kafka producer 시작됨 topic=%s", getattr(s, "kafka_recommendation_topic", ""))


async def stop_recommendation_kafka_producer() -> None:
    global _producer
    if _producer is None:
        return
    try:
        await _producer.stop()
    except Exception:
        logger.exception("추천용 Kafka producer 종료 중 오류")
    finally:
        _producer = None
        logger.info("추천용 Kafka producer 종료됨")


def get_recommendation_kafka_producer() -> Any:
    """시작된 공유 producer. 없으면 None (스크립트·미설정 환경)."""
    return _producer
