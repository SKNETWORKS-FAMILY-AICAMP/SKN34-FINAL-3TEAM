"""서비스 설정. 비밀 값은 환경 변수로만 주입."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "report-service"
    internal_token: str
    rabbitmq_url: str = "amqp://localhost:5672/"
    # P12: 재시도 3회(1·5·15분). definitions.json의 <큐>.retry.1~3 개수와 일치
    consumer_max_retries: int = 3
    # 레플리카 수 × prefetch = learning·ai 동시 호출 상한, 값은 실측 후 결정 (아키텍처 4.4)
    consumer_prefetch: int = 1
    http_connect_timeout: float = 2.0
    http_read_timeout: float = 30.0  # [P12] 확정 전 임시값
    database_url: str
    learning_url: str = "http://localhost:8081"
    ai_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
