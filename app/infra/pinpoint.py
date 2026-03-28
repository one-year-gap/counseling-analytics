from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from app.core.config import Settings
from app.infra.pinpoint_tracing import install_hybrid_trace_context

_PINPOINT_INIT_LOCK = Lock()
_PINPOINT_INITIALIZED = False


def build_fastapi_pinpoint_middleware(settings: Settings) -> list[Any]:
    if not settings.pinpoint_enabled:
        return []

    collector_agent_uri = settings.pinpoint_collector_agent_uri.strip()
    if not collector_agent_uri:
        logging.warning("Pinpoint is enabled but PINPOINT_COLLECTOR_AGENT_URI is empty. Skipping Pinpoint startup.")
        return []

    try:
        from starlette.middleware import Middleware
        from starlette_context.middleware import ContextMiddleware
        from pinpointPy import set_agent
        from pinpointPy.Fastapi import (
            PinPointMiddleWare,
            async_monkey_patch_for_pinpoint,
        )
    except ImportError:
        logging.exception("Pinpoint Python dependencies are not installed. Skipping Pinpoint startup.")
        return []

    _initialize_pinpoint(
        settings=settings,
        collector_agent_uri=collector_agent_uri,
        set_agent=set_agent,
        async_monkey_patch_for_pinpoint=async_monkey_patch_for_pinpoint,
    )

    return [
        Middleware(ContextMiddleware),
        Middleware(PinPointMiddleWare),
    ]


def _initialize_pinpoint(
    settings: Settings,
    collector_agent_uri: str,
    set_agent: Any,
    async_monkey_patch_for_pinpoint: Any,
) -> None:
    global _PINPOINT_INITIALIZED

    if _PINPOINT_INITIALIZED:
        return

    with _PINPOINT_INIT_LOCK:
        if _PINPOINT_INITIALIZED:
            return

        set_agent(
            settings.pinpoint_agent_id,
            settings.pinpoint_application_name,
            collector_agent_uri,
            settings.pinpoint_trace_limit,
            settings.pinpoint_timeout_ms,
            _resolve_log_level(settings.pinpoint_log_level),
        )
        install_hybrid_trace_context()
        async_monkey_patch_for_pinpoint(AioRedis=False, httpx=True)
        logging.info(
            "Pinpoint Python agent initialized app=%s agent=%s collector=%s",
            settings.pinpoint_application_name,
            settings.pinpoint_agent_id,
            collector_agent_uri,
        )
        _PINPOINT_INITIALIZED = True


def _resolve_log_level(value: str) -> int:
    return getattr(logging, (value or "INFO").upper(), logging.INFO)
