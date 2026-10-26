"""앱 조립: 예외 핸들러·내부 인증·라우터·AMQP·DB 연결 수명 주기."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine, text

from app.config import get_settings
from app.database import create_db_engine, create_session_factory
from app.errors import register_error_handlers
from app.health.router import router as health_router
from app.messaging.connection import AmqpConnection
from app.security import InternalAuthMiddleware


def _ping(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - readiness는 연결 가능 여부만 반환
        return False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    amqp = AmqpConnection(get_settings().rabbitmq_url)
    amqp.start()
    engine = create_db_engine()
    app.state.amqp = amqp
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    async def rabbitmq_ready() -> bool:
        return amqp.is_connected

    async def database_ready() -> bool:
        return await asyncio.to_thread(_ping, engine)

    app.state.readiness_checks = {"rabbitmq": rabbitmq_ready, "database": database_ready}
    try:
        yield
    finally:
        try:
            await amqp.close()
        finally:
            engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().service_name, lifespan=lifespan)
    register_error_handlers(app)
    app.add_middleware(InternalAuthMiddleware)
    app.include_router(health_router)
    # 기능 라우터는 여기에 등록
    return app
