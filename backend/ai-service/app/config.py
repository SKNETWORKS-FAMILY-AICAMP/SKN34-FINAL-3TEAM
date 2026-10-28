"""서비스 설정. 비밀 값은 환경 변수로만 주입."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "ai-service"
    internal_token: str
    rabbitmq_url: str = "amqp://localhost:5672/"
    http_connect_timeout: float = 2.0
    http_read_timeout: float = 30.0  # 내부 호출 기본값 (P12 목록 밖)
    learning_url: str = "http://localhost:8081"
    scoring_url: str = "http://localhost:8001"
    core_url: str = "http://localhost:8080"

    # LLM: 제공자 교체는 llm_provider만 변경, 키·모델은 제공자별로 보관
    llm_provider: str = "openai"
    anthropic_api_key: str | None = None  # 비어 있으면 503 AI_UNAVAILABLE
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_effort: str = "medium"  # low|medium|high|xhigh|max, 학생 대기 시간 고려
    anthropic_fallback: bool = True  # 안전 거절 시 Anthropic 권장 모델로 자동 재처리
    # OpenAI 또는 OpenAI 호환 sLLM 서버(vLLM·Ollama 등). 모델이 비어 있으면 503 AI_UNAVAILABLE
    openai_api_key: str | None = None  # sLLM 서버(openai_base_url 지정)는 비워도 됨
    openai_model: str = "gpt-6.1-terra"  # 판정·되묻기 실제 호출 확인 (2026-10-27)
    openai_base_url: str | None = None  # 비우면 OpenAI 기본 주소
    openai_json_mode: Literal["json_schema", "json_object"] = "json_schema"  # sLLM은 json_object
    # 판정 최악 15 + 1 + 15 = 31초 < learning→ai 35초 (P12)
    llm_timeout: float = 15.0  # LLM 1회 15초 (P12)
    llm_max_retries: int = 1  # 재시도 1회 (P12)
    llm_retry_backoff: float = 1.0  # 재시도 전 1초 대기 (P12)

    # 판정·되묻기
    judge_require_verified: bool = False  # 사람 검증(judge_verified) 도입 시 true
    # 아래는 P12 목록 밖의 ai 담당 결정값
    judge_min_answer_length: int = 10  # TOO_SHORT 기준 (공백 제외 글자 수)
    followup_leak_max_retries: int = 1  # 유출 검사 실패 시 재생성 1회 (P16)
    followup_example_overlap_chars: int = 12  # 예시 답과 이만큼(공백·문장부호 제외) 겹치면 유출
    # 되묻기 전체 마감(초). learning→ai 되묻기 35초(P12)보다 짧게, 재생성은 이 안에서만
    followup_deadline: float = 33.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
