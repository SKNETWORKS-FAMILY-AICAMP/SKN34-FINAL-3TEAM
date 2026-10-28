"""앱 조립: 예외 핸들러·내부 인증·라우터·AMQP 연결 수명 주기."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.clients.model_artifacts import S3ModelArtifacts
from app.config import get_settings
from app.errors import register_error_handlers
from app.health.router import router as health_router
from app.messaging.connection import AmqpConnection
from app.model_loader import ModelLoader
from app.model_registry import ModelRegistry
from app.model_startup import ModelStartup
from app.security import InternalAuthMiddleware
from app.versions import router as versions_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    amqp = AmqpConnection(settings.rabbitmq_url)
    amqp.start()
    app.state.amqp = amqp

    async def rabbitmq_ready() -> bool:
        return amqp.is_connected

    async with internal_client(settings.core_url) as http:
        registry = ModelRegistry(ModelLoader(S3ModelArtifacts(settings)))
        startup = ModelStartup(CoreClient(http), registry, settings.model_retry_interval)
        app.state.model_registry = registry
        app.state.readiness_checks = {"rabbitmq": rabbitmq_ready, "models": startup.is_ready}
        startup.start()
        try:
            yield
        finally:
            await startup.close()
            await amqp.close()


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().service_name, lifespan=lifespan)
    register_error_handlers(app)
    app.add_middleware(InternalAuthMiddleware)
    app.include_router(health_router)
    app.include_router(versions_router)
    # 기능 라우터는 여기에 등록
    return app
