"""서비스 설정. 비밀 값은 환경 변수로만 주입."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "report-service"
    internal_token: str  # 이 서비스가 내부 호출에 보내는 자기 토큰
    # 받는 쪽 허용 호출자 토큰 (security.CALLER_PATHS). 빈 값이면 그 호출자 거부
    internal_token_core: str = ""
    rabbitmq_url: str = "amqp://localhost:5672/"
    # P12: 재시도 3회(1·5·15분). definitions.json의 <큐>.retry.1~3 개수와 일치
    consumer_max_retries: int = 3
    # 레플리카 수 × prefetch = learning·ai 동시 호출 상한, 값은 실측 후 결정 (아키텍처 4.4)
    consumer_prefetch: int = 1
    # 발행 완료 outbox_event·processed_event 보존 일수 (#208)
    event_retention_days: int = Field(default=90, ge=1)
    http_connect_timeout: float = 2.0
    http_read_timeout: float = 30.0  # 내부 호출 기본값 (P12 목록 밖)
    database_url: str
    learning_url: str = "http://localhost:8081"
    ai_url: str = "http://localhost:8000"
    core_url: str = "http://localhost:8080"
    s3_endpoint_url: str | None = None
    s3_public_endpoint_url: str | None = None
    s3_bucket: str = "sagomungchi-local-reports"
    s3_region: str = "ap-northeast-2"
    # Deploy with the #385/#391 learning producer; false is an explicit rollback switch.
    report_theme_summary_enabled: bool = True
    # #747: ai는 SageMaker 실시간 호출 1회(60초 제한, 읽기 70초)에 마감 75초. 대기는 그보다 길게.
    # 설명은 주당 최대 3건이라 예산은 3 × 80초 + learning 조회 여유
    report_narrative_timeout_seconds: float = Field(default=80.0, gt=0, le=300)
    report_explanation_timeout_seconds: float = Field(default=80.0, gt=0, le=300)
    report_explanation_budget_seconds: float = Field(default=300.0, gt=0, le=900)
    report_download_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    # 추억 그림책 (docs/proposals/memory-book.md).
    # 그림 허용 출처(scheme://host[:port], 쉼표). 비면 그림 없이 만든다.
    # 내부 주소는 "공개 출처=클러스터 안 출처" 쉼표 목록(로컬 kind 전용)
    memory_book_asset_origins: str = ""
    memory_book_asset_internal_origins: str = ""
    memory_book_image_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1)
    memory_book_total_max_bytes: int = Field(default=40 * 1024 * 1024, ge=1)
    memory_book_asset_timeout_seconds: float = Field(default=10.0, gt=0, le=60)


@lru_cache
def get_settings() -> Settings:
    return Settings()
