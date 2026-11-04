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
    scoring_url: str = "http://localhost:8001"  # #69 M2/M1 교차 확인 (api-spec 4.2.2)
    core_url: str = "http://localhost:8080"  # #68 활성 버전 조회 연결용으로 유지

    # #171: LLM 메타데이터만 Collector를 거쳐 Langfuse로 전송한다.
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_otlp_endpoint: str | None = None  # OTLP/HTTP /v1/traces 전체 URL

    # LLM: 제공자 교체는 llm_provider만 변경, 키·모델은 제공자별로 보관
    llm_provider: str = "openai"
    anthropic_api_key: str | None = None  # 비어 있으면 503 AI_UNAVAILABLE
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_effort: str = "medium"  # low|medium|high|xhigh|max, 학생 대기 시간 고려
    anthropic_fallback: bool = True  # 안전 거절 시 Anthropic 권장 모델로 자동 재처리
    # OpenAI 또는 OpenAI 호환 sLLM 서버(vLLM·Ollama 등). 모델이 비어 있으면 503 AI_UNAVAILABLE
    openai_api_key: str | None = None  # sLLM 서버(openai_base_url 지정)는 비워도 됨
    openai_model: str = "gpt-6-luna"  # 판정·되묻기 실제 호출 확인 (2026-10-27)
    openai_base_url: str | None = None  # 비우면 OpenAI 기본 주소
    openai_json_mode: Literal["json_schema", "json_object"] = "json_schema"  # sLLM은 json_object
    # LLM 최악 15 + 1 + 15 = 31초. 판정은 judge_deadline 33초 안에서 scoring 몫을 먼저 떼어
    # LLM 30초(두 번째 시도 14초로 줄어듦) + scoring 3초 = 33초 < learning→ai 35초 (P12)
    llm_timeout: float = 15.0  # LLM 1회 15초 (P12)
    llm_max_retries: int = 1  # 재시도 1회 (P12)
    llm_retry_backoff: float = 1.0  # 재시도 전 1초 대기 (P12)

    # 판정·되묻기
    judge_require_verified: bool = False  # 사람 검증(judge_verified) 도입 시 true
    # 아래는 P12 목록 밖의 ai 담당 결정값
    judge_min_answer_length: int = 10  # TOO_SHORT 기준 (공백 제외 글자 수)
    # #69 판정 모델 교차 확인 (api-spec 4.2.2). 판정 전체 마감은 learning→ai 35초(P12)보다 짧게
    judge_deadline: float = 33.0
    scoring_timeout: float = 10.0  # scoring 호출 1회 한도, 남은 마감 시간과 작은 값을 씀
    # M2·M1 입력이 있으면 LLM 추출 마감을 이만큼 앞당겨 scoring 몫으로 남김 (#87 예열 후 최대 1.7초)
    scoring_reserve: float = 3.0
    m2_cross_check_enabled: bool = False  # false면 M2(scoring)를 부르지 않음 (#305)
    # 불일치 경계(임시, M2 담당 확인 전): scores 평균. 서술 9항목 1~5(hol 1~4), 논술 3영역 0~3
    m2_narrative_low: float = 2.0
    m2_narrative_high: float = 4.0
    m2_essay_low: float = 1.0
    m2_essay_high: float = 2.0
    m1_check_enabled: bool = False  # scoring M1 미학습(#88) 동안 꺼 둠
    m1_min_confidence: float = 0.8  # 미만이면 HELD(LOW_CONFIDENCE) (P15)
    followup_leak_max_retries: int = 1  # 유출 검사 실패 시 재생성 1회 (P16)
    followup_example_overlap_chars: int = 12  # 예시 답과 이만큼(공백·문장부호 제외) 겹치면 유출
    # 되묻기 전체 마감(초). learning→ai 되묻기 35초(P12)보다 짧게, 재생성은 이 안에서만
    followup_deadline: float = 33.0
    # 리포트 서술 전체 마감(초). report→ai 읽기 30초보다 짧게, 재시도는 남은 시간 안에서만
    narrative_deadline: float = 28.0

    # 미션 초안 생성 (#354, api-spec 4.2). 호출 1번에 생성 1회, 반복은 learning
    # 미션 초안만 P12 예외(#353): 주기 작업이라 기다리는 사람이 없고, 기본 모델 gpt-6-luna가
    # 실제 성취기준으로 15~31.7초 걸림(14건). LLM 60초 1회, 마감 63초(learning 초안 ai 대기 70초 안)
    mission_draft_deadline: float = 63.0
    mission_draft_llm_timeout: float = 60.0
    mission_draft_llm_retries: int = 0
    mission_draft_max_tokens: int = 8192  # gpt-6-luna 실측 출력 최대 3,514토큰(4096에 가까움)
    # 학년별 질문 글자 수 상한 (QUESTION_LENGTH). P19(김동섭) 확정 전 MVP 기준안:
    # 데모 시드 최대 193자에 여유
    mission_draft_question_max_chars: dict[int, int] = {3: 200, 4: 200, 5: 200, 6: 200}

    # 분석 대화 전체 마감(초). core 기준 전체 120초(P12)보다 짧게, LLM 호출은 이 안에서만
    analysis_deadline: float = 110.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
