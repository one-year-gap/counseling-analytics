from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator

try:
    from starlette_context import context as starlette_context
except Exception:  # pragma: no cover
    starlette_context = None  # type: ignore[assignment]

try:
    from pinpointPy import Defines, pinpoint
    from pinpointPy.TraceContext import TraceContext, set_trace_context
except Exception:  # pragma: no cover
    Defines = None  # type: ignore[assignment]
    pinpoint = None  # type: ignore[assignment]
    TraceContext = object  # type: ignore[assignment]
    set_trace_context = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_PINPOINT_PARENT_ID: ContextVar[int] = ContextVar("pinpoint_parent_id", default=0)


def _pinpoint_enabled() -> bool:
    return pinpoint is not None and Defines is not None and set_trace_context is not None


class HybridTraceContext(TraceContext):
    """Use request-local Starlette context when available, and fall back to ContextVar."""

    def get_parent_id(self) -> tuple[bool, int]:
        request_parent_id = 0
        if starlette_context is not None:
            try:
                request_parent_id = int(starlette_context.get("_pinpoint_id_", 0) or 0)
            except Exception:
                request_parent_id = 0

        if request_parent_id > 0:
            return True, request_parent_id

        fallback_parent_id = _PINPOINT_PARENT_ID.get()
        if fallback_parent_id > 0:
            return True, fallback_parent_id

        return False, -1

    def set_parent_id(self, id: int) -> None:
        value = id if id > 0 else 0
        _PINPOINT_PARENT_ID.set(value)
        if starlette_context is not None:
            try:
                starlette_context["_pinpoint_id_"] = value
            except Exception:
                pass


_HYBRID_TRACE_CONTEXT = HybridTraceContext()


@dataclass(frozen=True)
class TraceSnapshot:
    transaction_id: str
    parent_span_id: str
    parent_name: str
    parent_type: str
    parent_host: str


def install_hybrid_trace_context() -> None:
    if not _pinpoint_enabled():
        return
    set_trace_context(_HYBRID_TRACE_CONTEXT)


def current_trace_id() -> int:
    if not _pinpoint_enabled():
        return 0
    sampled, trace_id = _HYBRID_TRACE_CONTEXT.get_parent_id()
    return trace_id if sampled else 0


def capture_current_trace_snapshot() -> TraceSnapshot | None:
    if not _pinpoint_enabled():
        return None

    trace_id = current_trace_id()
    if trace_id <= 0:
        return None

    transaction_id = pinpoint.get_context(Defines.PP_TRANSCATION_ID, trace_id) or ""
    parent_span_id = pinpoint.get_context(Defines.PP_SPAN_ID, trace_id) or ""
    if not transaction_id or not parent_span_id:
        return None

    app_name = pinpoint.app_name() or "intelligence-server"
    return TraceSnapshot(
        transaction_id=str(transaction_id),
        parent_span_id=str(parent_span_id),
        parent_name=app_name,
        parent_type=Defines.PYTHON,
        parent_host=app_name,
    )


def _normalize_sql(value: Any) -> str:
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(raw) <= 4096:
        return raw
    return raw[:4093] + "..."


def resolve_postgresql_destination(resource: Any, fallback: str = "postgresql") -> str:
    addr = getattr(resource, "_addr", None)
    if isinstance(addr, tuple) and addr:
        host = str(addr[0] or "").strip()
        port = addr[1] if len(addr) > 1 else None
        if host and port:
            return f"{host}:{port}"
        if host:
            return host

    params = getattr(resource, "_params", None)
    host = str(getattr(params, "host", "") or "").strip()
    port = getattr(params, "port", None)
    if host and port:
        return f"{host}:{port}"
    if host:
        return host

    return fallback


def resolve_kafka_destination(bootstrap_servers: str, topic: str) -> str:
    topic_name = str(topic or "").strip()
    if topic_name:
        return topic_name

    first_target = str(bootstrap_servers or "").split(",", 1)[0].strip()
    return first_target or "kafka"


def _reset_parent_id(previous_parent_id: int) -> None:
    _HYBRID_TRACE_CONTEXT.set_parent_id(previous_parent_id)


@asynccontextmanager
async def traced_root_transaction(
    name: str,
    request_uri: str,
    *,
    snapshot: TraceSnapshot | None = None,
    request_server: str = "intelligence-server",
    request_client: str = "background",
) -> AsyncIterator[int | None]:
    if not _pinpoint_enabled():
        yield None
        return

    previous_parent_id = _PINPOINT_PARENT_ID.get()
    trace_id = pinpoint.with_trace(0)
    _HYBRID_TRACE_CONTEXT.set_parent_id(trace_id)

    try:
        span_id = pinpoint.gen_sid()
        transaction_id = snapshot.transaction_id if snapshot is not None else pinpoint.gen_tid()

        pinpoint.add_trace_header(Defines.PP_INTERCEPTOR_NAME, name, trace_id)
        pinpoint.add_trace_header(Defines.PP_APP_NAME, pinpoint.app_name(), trace_id)
        pinpoint.add_context(Defines.PP_APP_NAME, pinpoint.app_name(), trace_id)
        pinpoint.add_trace_header(Defines.PP_APP_ID, pinpoint.app_id(), trace_id)
        pinpoint.add_trace_header(Defines.PP_REQ_URI, request_uri, trace_id)
        pinpoint.add_trace_header(Defines.PP_REQ_SERVER, request_server, trace_id)
        pinpoint.add_trace_header(Defines.PP_REQ_CLIENT, request_client, trace_id)
        pinpoint.add_trace_header(Defines.PP_SERVER_TYPE, Defines.PYTHON, trace_id)
        pinpoint.add_context(Defines.PP_SERVER_TYPE, Defines.PYTHON, trace_id)
        pinpoint.add_context(Defines.PP_HEADER_PINPOINT_SAMPLED, Defines.PP_SAMPLED, trace_id)
        pinpoint.add_trace_header(Defines.PP_TRANSCATION_ID, transaction_id, trace_id)
        pinpoint.add_context(Defines.PP_TRANSCATION_ID, transaction_id, trace_id)
        pinpoint.add_trace_header(Defines.PP_SPAN_ID, span_id, trace_id)
        pinpoint.add_context(Defines.PP_SPAN_ID, span_id, trace_id)

        if snapshot is not None:
            pinpoint.add_trace_header(Defines.PP_PARENT_SPAN_ID, snapshot.parent_span_id, trace_id)
            pinpoint.add_trace_header(Defines.PP_PARENT_NAME, snapshot.parent_name, trace_id)
            pinpoint.add_trace_header(Defines.PP_PARENT_TYPE, snapshot.parent_type, trace_id)
            pinpoint.add_trace_header(Defines.PP_PARENT_HOST, snapshot.parent_host, trace_id)

        yield trace_id
    except Exception as exc:
        pinpoint.mark_as_error(str(exc), "", 0, trace_id)
        raise
    finally:
        pinpoint.end_trace(trace_id)
        _reset_parent_id(previous_parent_id)


@asynccontextmanager
async def traced_external_span(
    name: str,
    server_type: str,
    destination: str,
    *,
    sql: str | None = None,
    topic: str | None = None,
    args_value: str | None = None,
) -> AsyncIterator[int | None]:
    if not _pinpoint_enabled():
        yield None
        return

    parent_trace_id = current_trace_id()
    if parent_trace_id <= 0:
        yield None
        return

    previous_parent_id = _PINPOINT_PARENT_ID.get()
    trace_id = pinpoint.with_trace(parent_trace_id)
    _HYBRID_TRACE_CONTEXT.set_parent_id(trace_id)

    try:
        pinpoint.add_trace_header(Defines.PP_INTERCEPTOR_NAME, name, trace_id)
        pinpoint.add_trace_header(Defines.PP_SERVER_TYPE, server_type, trace_id)
        pinpoint.add_trace_header(Defines.PP_DESTINATION, destination, trace_id)

        if sql:
            pinpoint.add_trace_header(Defines.PP_SQL_FORMAT, _normalize_sql(sql), trace_id)
        if topic:
            pinpoint.add_trace_header(Defines.PP_KAFKA_TOPIC, topic, trace_id)
        if args_value:
            pinpoint.add_trace_header_v2(Defines.PP_ARGS, args_value, trace_id)

        yield trace_id
    except Exception as exc:
        pinpoint.add_exception(str(exc), trace_id)
        raise
    finally:
        pinpoint.end_trace(trace_id)
        _reset_parent_id(previous_parent_id)
