"""앱 조립: 예외 핸들러·내부 인증·라우터·AMQP 연결 수명 주기."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import openai
from fastapi import FastAPI
from langfuse import Langfuse
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from app import tracing
from app.analysis_agent.router import router as analysis_router
from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.clients.scoring_client import ScoringClient
from app.config import get_settings
from app.embedding.router import router as embedding_router
from app.errors import register_error_handlers
from app.followup.router import router as followup_router
from app.health.router import router as health_router
from app.http_telemetry import HttpTelemetryMiddleware
from app.judgment.router import router as judgment_router
from app.llm.embeddings import create_embedder
from app.llm.media import create_media_clients
from app.llm.providers import create_explanation_llm, create_llm, create_theme_llms
from app.llm.report import create_report_llm
from app.memory_explanation.router import router as memory_explanation_router
from app.memory_query.router import router as memory_query_router
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
from app.theme_draft.storage import create_storage
from app.word_help.dictionary import Dictionary
from app.word_help.router import router as word_help_router
from app.word_help.web_search import WordWebSearch


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # 앱 trace·지표 (#1029). 전역 provider가 아니라 Langfuse 전역 provider와 섞이지 않는다
    tracing.configure()
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
    app.state.report_llm = create_report_llm(settings, usage_recorder)
    app.state.report_llm.langfuse = langfuse
    # Summary and detailed report text are pinned to the same LoRA endpoint.
    app.state.explanation_llm = create_explanation_llm(settings, recorder=usage_recorder)
    app.state.explanation_llm.langfuse = langfuse
    # 주간 테마 초안 생성·검토 (#437). 모델은 테마 전용 설정, 같은 OpenAI 키
    app.state.theme_llm, app.state.theme_review_llm = create_theme_llms(settings, usage_recorder)
    app.state.theme_llm.langfuse = langfuse
    app.state.theme_review_llm.langfuse = langfuse
    # 테마 그림·영상·S3 (#437). 버킷이 비면 None이라 그림·영상·움직임을 건너뛰고 경고만
    app.state.theme_image, app.state.theme_video = create_media_clients(settings, usage_recorder)
    app.state.theme_storage = create_storage(settings)
    # 임베딩 (#467). 사용량 callType은 purpose로 KNOWLEDGE_EMBEDDING·MEMORY_EMBEDDING(#565)
    app.state.embedder = create_embedder(settings, recorder=usage_recorder)
    # 낱말 물어보기 사전 (#599). 키가 없으면 그 요청만 503 DICTIONARY_UNAVAILABLE
    app.state.dictionary = Dictionary(
        settings.dict_korean_api,
        settings.dict_korean_api_key,
        settings.kli_korean_api,
        settings.kli_korean_api_key,
    )

    async def rabbitmq_ready() -> bool:
        return amqp.is_connected

    async with (
        internal_client(settings.core_url) as http,
        internal_client(settings.scoring_url) as scoring_http,
        httpx.AsyncClient(timeout=3.0) as word_source_http,
    ):
        search_client = (
            openai.AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url="https://api.openai.com/v1",
                max_retries=0,
            )
            if settings.word_help_provider == "llm" and settings.openai_api_key
            else None
        )
        app.state.word_web_search = (
            WordWebSearch(search_client, word_source_http, usage_recorder)
            if search_client is not None
            else None
        )
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
            if search_client is not None:
                await search_client.close()
            await consumer.close()
            await usage_recorder.close()
            await amqp.close()
            if langfuse is not None:
                langfuse.shutdown()
            tracing.shutdown()


def create_app() -> FastAPI:
    # 문서 경로는 인증 미들웨어(/internal/만 검사) 밖이라 끈다 (#1053). 계약은 contracts/openapi
    app = FastAPI(
        title=get_settings().service_name,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    register_error_handlers(app)
    app.add_middleware(InternalAuthMiddleware)
    # 마지막에 넣어 가장 바깥: 401·403도 재고, 서버 span 안에서 인증·처리가 돈다
    app.add_middleware(HttpTelemetryMiddleware)
    app.include_router(health_router)
    # 기능 라우터는 여기에 등록
    app.include_router(judgment_router)
    app.include_router(followup_router)
    app.include_router(mission_draft_router)
    app.include_router(theme_draft_router)
    app.include_router(analysis_router)
    app.include_router(report_narrative_router)
    app.include_router(report_explanation_router)
    app.include_router(embedding_router)
    app.include_router(memory_explanation_router)
    app.include_router(memory_query_router)
    app.include_router(word_help_router)
    app.include_router(versions_router)
    return app
