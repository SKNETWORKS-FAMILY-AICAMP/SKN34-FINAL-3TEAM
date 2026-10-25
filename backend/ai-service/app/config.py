"""서비스 설정. 비밀 값은 환경 변수로만 주입."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "ai-service"
    internal_token: str
    rabbitmq_url: str = "amqp://localhost:5672/"
    http_connect_timeout: float = 2.0
    http_read_timeout: float = 30.0  # [P12] 확정 전 임시값
    learning_url: str = "http://localhost:8081"
    scoring_url: str = "http://localhost:8001"
    core_url: str = "http://localhost:8080"


@lru_cache
def get_settings() -> Settings:
    return Settings()
