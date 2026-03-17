"""FastAPI entrypoint for the ephemeral analysis server (CDC 기반)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.cdc_analysis_service import CdcAnalysisService 

settings = get_settings()
configure_logging(settings.debug)


@asynccontextmanager
async def lifespan(application: FastAPI):
    cdc_service = CdcAnalysisService(settings)
    await cdc_service.start()
    application.state.cdc_service = cdc_service
    
    try:
        yield
    finally:
        await cdc_service.stop()


def create_app() -> FastAPI:
    # lifespan을 등록해서 FastAPI 서버와 CDC 데몬의 생명주기를 하나로 묶음
    application = FastAPI(title=f"{settings.app_name}-analysis-server", lifespan=lifespan)

    @application.get("/")
    async def root() -> dict[str, str]:
        return {"app": settings.app_name, "mode": "cdc-analysis-server", "health": "/health"}

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "cdc_analysis_service_running"}

    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.analysis_server.main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
    )


if __name__ == "__main__":
    run()