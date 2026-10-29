"""서비스 설정. 비밀 값은 환경 변수로만 주입."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "scoring-service"
    internal_token: str
    rabbitmq_url: str = "amqp://localhost:5672/"
    http_connect_timeout: float = 2.0
    http_read_timeout: float = 30.0  # 내부 호출 기본값 (P12 목록 밖)
    core_url: str = "http://localhost:8080"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "sagomungchi-local-models"
    s3_region: str = "ap-northeast-2"
    model_cache_dir: Path = Path("local_data/scoring-models")
    model_retry_interval: float = Field(default=5.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
