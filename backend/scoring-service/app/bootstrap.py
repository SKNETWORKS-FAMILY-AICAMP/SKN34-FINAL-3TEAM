"""앱 조립: 예외 핸들러·내부 인증·라우터·AMQP 연결 수명 주기."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.errors import register_error_handlers
from app.health.router import router as health_router
from app.messaging.connection import AmqpConnection
from app.security import InternalAuthMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    amqp = AmqpConnection(get_settings().rabbitmq_url)
    amqp.start()
    app.state.amqp = amqp

    async def rabbitmq_ready() -> bool:
        return amqp.is_connected

    app.state.readiness_checks = {"rabbitmq": rabbitmq_ready}
    yield
    await amqp.close()


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().service_name, lifespan=lifespan)
    register_error_handlers(app)
    app.add_middleware(InternalAuthMiddleware)
    app.include_router(health_router)
    # 기능 라우터는 여기에 등록
    return app
