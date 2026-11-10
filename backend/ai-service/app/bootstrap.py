"""앱 조립: 예외 핸들러·내부 인증·라우터·AMQP 연결 수명 주기."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langfuse import Langfuse
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from app.analysis_agent.router import router as analysis_router
from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.clients.scoring_client import ScoringClient
from app.config import get_settings
from app.errors import register_error_handlers
from app.followup.router import router as followup_router
from app.health.router import router as health_router
from app.judgment.router import router as judgment_router
from app.llm.providers import create_explanation_llm, create_llm
from app.messaging.connection import AmqpConnection
from app.messaging.consumer import ModelVersionConsumer
from app.messaging.publisher import EventPublisher, UsagePublisher
from app.messaging.usage_recorder import BackgroundUsageRecorder
from app.mission_draft.router import router as mission_draft_router
from app.prompt_versions.registry import ActiveVersions
from app.prompt_versions.router import router as versions_router
from app.prompt_versions.service import PromptSync
from app.report_explanation.router import router as report_explanation_router
from app.report_narrative.router import router as report_narrative_router
from app.security import InternalAuthMiddleware
from app.theme_draft.router import router as theme_draft_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    langfuse: Langfuse | None = None
    if settings.langfuse_enabled:
        if not all(
            (
                settings.langfuse_public_key,
                settings.langfuse_secret_key,
                settings.langfuse_otlp_endpoint,
            )
        ):
            raise ValueError("Langfuse 계측에 public/secret key와 OTLP endpoint가 필요합니다")
        langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            span_exporter=OTLPSpanExporter(endpoint=settings.langfuse_otlp_endpoint),
            should_export_span=lambda span: span.instrumentation_scope.name == "langfuse-sdk",
        )
    amqp = AmqpConnection(settings.rabbitmq_url)
    amqp.start()
    app.state.amqp = amqp
    app.state.usage_publisher = UsagePublisher(
        EventPublisher(amqp), service="ai", source=settings.service_name
    )
    # LLM 요청마다 사용량 이벤트 발행 (백그라운드, best-effort)
    usage_recorder = BackgroundUsageRecorder(app.state.usage_publisher)
    app.state.llm = create_llm(settings, recorder=usage_recorder)
    app.state.llm.langfuse = langfuse
    # 리포트 설명만 클러스터 안 sLLM (#477). 다른 호출의 제공자는 그대로
    app.state.explanation_llm = create_explanation_llm(settings, recorder=usage_recorder)
    app.state.explanation_llm.langfuse = langfuse

    async def rabbitmq_ready() -> bool:
        return amqp.is_connected

    async with (
        internal_client(settings.core_url) as http,
        internal_client(settings.scoring_url) as scoring_http,
    ):
        # 판정 M2·M1 교차 확인 (#69). timeout은 요청마다 남은 판정 시간으로 정함
        app.state.scoring = ScoringClient(scoring_http)
        versions = ActiveVersions()
        consumer = ModelVersionConsumer(amqp, PromptSync(CoreClient(http), versions))
        app.state.active_versions = versions
        app.state.readiness_checks = {"rabbitmq": rabbitmq_ready, "versions": consumer.is_ready}
        consumer.start()
        try:
            yield
        finally:
            await consumer.close()
            await usage_recorder.close()
            await amqp.close()
            if langfuse is not None:
                langfuse.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().service_name, lifespan=lifespan)
    register_error_handlers(app)
    app.add_middleware(InternalAuthMiddleware)
    app.include_router(health_router)
    # 기능 라우터는 여기에 등록
    app.include_router(judgment_router)
    app.include_router(followup_router)
    app.include_router(mission_draft_router)
    app.include_router(theme_draft_router)
    app.include_router(analysis_router)
    app.include_router(report_narrative_router)
    app.include_router(report_explanation_router)
    app.include_router(versions_router)
    return app
