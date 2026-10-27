"""앱 조립: 예외 핸들러·내부 인증·라우터·AMQP 연결 수명 주기."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.errors import register_error_handlers
from app.followup.router import router as followup_router
from app.health.router import router as health_router
from app.judgment.router import router as judgment_router
from app.llm.providers import create_llm
from app.messaging.connection import AmqpConnection
from app.messaging.publisher import EventPublisher, UsagePublisher
from app.messaging.usage_recorder import BackgroundUsageRecorder
from app.security import InternalAuthMiddleware
from app.versions import router as versions_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    amqp = AmqpConnection(settings.rabbitmq_url)
    amqp.start()
    app.state.amqp = amqp
    app.state.usage_publisher = UsagePublisher(
        EventPublisher(amqp), service="ai", source=settings.service_name
    )
    # LLM 요청마다 사용량 이벤트 발행 (백그라운드, best-effort)
    usage_recorder = BackgroundUsageRecorder(app.state.usage_publisher)
    app.state.llm = create_llm(settings, recorder=usage_recorder)

    async def rabbitmq_ready() -> bool:
        return amqp.is_connected

    app.state.readiness_checks = {"rabbitmq": rabbitmq_ready}
    yield
    await usage_recorder.close()
    await amqp.close()


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().service_name, lifespan=lifespan)
    register_error_handlers(app)
    app.add_middleware(InternalAuthMiddleware)
    app.include_router(health_router)
    # 기능 라우터는 여기에 등록
    app.include_router(judgment_router)
    app.include_router(followup_router)
    app.include_router(versions_router)
    return app
