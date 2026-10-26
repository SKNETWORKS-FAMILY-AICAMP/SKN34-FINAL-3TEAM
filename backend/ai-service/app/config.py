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

    # LLM: 제공자 교체는 llm_provider만 변경, 키·모델은 제공자별로 보관
    llm_provider: str = "anthropic"
    anthropic_api_key: str | None = None  # 비어 있으면 503 AI_UNAVAILABLE
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_effort: str = "medium"  # low|medium|high|xhigh|max, 학생 대기 시간 고려
    anthropic_fallback: bool = True  # 안전 거절 시 Anthropic 권장 모델로 자동 재처리
    llm_timeout: float = 30.0  # [P12] 확정 전 임시값
    llm_max_retries: int = 2  # [P12] 확정 전 임시값
    llm_retry_backoff: float = 0.5  # [P12] 확정 전 임시값, 재시도마다 2배 (0.5초 → 1초)

    # 판정·되묻기
    judge_require_verified: bool = False  # 사람 검증(judge_verified) 도입 시 true
    judge_min_answer_length: int = 10  # [P12] 확정 전 임시값, TOO_SHORT 기준 (공백 제외 글자 수)
    followup_leak_max_retries: int = 2  # [P12] 확정 전 임시값
    # [P12] 확정 전 임시값, 예시 답과 이만큼(공백·문장부호 제외 글자 수) 겹치면 유출
    followup_example_overlap_chars: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
