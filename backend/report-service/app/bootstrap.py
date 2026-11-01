"""앱 조립: 예외 핸들러·내부 인증·라우터·DB 연결 수명 주기.

조회 API는 AMQP를 쓰지 않는다(발행·소비는 worker).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine, text

from app.clients.base import internal_client
from app.clients.learning_client import LearningClient
from app.clients.storage import ObjectStorage
from app.concurrency import run_blocking
from app.config import get_settings
from app.database import create_db_engine, create_session_factory
from app.errors import install_problem_openapi, register_error_handlers
from app.generation.router import router as reconciliation_router
from app.health.router import router as health_router
from app.query.router import router as query_router
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
    engine = create_db_engine()
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    async def database_ready() -> bool:
        return await asyncio.to_thread(_ping, engine)

    app.state.readiness_checks = {"database": database_ready}
    try:
        async with AsyncExitStack() as clients:
            http = await clients.enter_async_context(internal_client(get_settings().learning_url))
            storage = await run_blocking(ObjectStorage.configured)
            clients.push_async_callback(run_blocking, storage.close)
            app.state.learning_client = LearningClient(http)
            app.state.storage = storage
            yield
    finally:
        engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().service_name, lifespan=lifespan)
    register_error_handlers(app)
    install_problem_openapi(app)
    app.add_middleware(InternalAuthMiddleware)
    app.include_router(health_router)
    app.include_router(query_router)
    app.include_router(reconciliation_router)
    # 기능 라우터는 여기에 등록
    return app
