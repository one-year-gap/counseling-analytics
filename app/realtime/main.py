"""FastAPI application entrypoint for realtime recommendation API."""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infra.kafka.recommendation_producer import (
    start_recommendation_kafka_producer,
    stop_recommendation_kafka_producer,
)
from app.realtime.api.router import api_router
from app.services.cdc_analysis_service import CdcAnalysisService

settings = get_settings()
configure_logging(settings.debug)


def _mask_database_url(url: str) -> str:
    """비밀번호만 마스킹한 URL (연결 대상 확인용)."""
    if not url:
        return "(empty)"
    return re.sub(r"(:[^:@]+)(@)", r":****\2", url, count=1)


@asynccontextmanager
async def lifespan(application: FastAPI):
    runtime_settings = get_settings()
    cdc_service = None

    if runtime_settings.cdc_analysis_enabled:
        cdc_service = CdcAnalysisService(runtime_settings)
        await cdc_service.start()
        application.state.cdc_service = cdc_service
        logging.info("CDC analysis service enabled inside unified intelligence runtime.")

    await start_recommendation_kafka_producer(runtime_settings)

    try:
        yield
    finally:
        await stop_recommendation_kafka_producer()
        if cdc_service is not None:
            await cdc_service.stop()


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.on_event("startup")
    async def log_db_target() -> None:
        runtime_settings = get_settings()
        url = runtime_settings.effective_database_url
        logging.info("DB 연결 대상: %s", _mask_database_url(url))
        logging.info("CDC analysis enabled: %s", runtime_settings.cdc_analysis_enabled)

    @application.get("/")
    async def root() -> dict[str, str]:
        return {"app": settings.app_name, "mode": "intelligence-server", "docs": "/docs", "health": "/health"}

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.realtime.main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
    )


if __name__ == "__main__":
    run()
