"""앱 lifespan에서 유지하는 AsyncOpenAI 클라이언트 (연결 풀 재사용)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_client: Any = None


def start_openai_client(settings: Settings | None = None) -> None:
    """OPENAI_API_KEY가 있을 때만 공유 클라이언트를 만든다. 동기 함수(내부 I/O 없음)."""
    global _client
    if _client is not None:
        return
    s = settings or get_settings()
    api_key = (getattr(s, "openai_api_key", "") or "").strip()
    if not api_key:
        logger.info("OPENAI_API_KEY 비어 있음, 공유 AsyncOpenAI 클라이언트 생략")
        return
    from openai import AsyncOpenAI

    _client = AsyncOpenAI(api_key=api_key)
    logger.info("공유 AsyncOpenAI 클라이언트 생성됨")


async def stop_openai_client() -> None:
    global _client
    if _client is None:
        return
    try:
        await _client.close()
    except Exception:
        logger.exception("AsyncOpenAI close 중 오류")
    finally:
        _client = None
        logger.info("공유 AsyncOpenAI 클라이언트 종료됨")


def get_openai_client() -> Any:
    """lifespan에서 초기화된 클라이언트. 없으면 None (스크립트·키 미설정 기동)."""
    return _client
