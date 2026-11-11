"""서비스 설정. 비밀 값은 환경 변수로만 주입."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
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

    # 주간 테마 초안 생성 (#437, api-spec 4.2). 호출 1번에 그래프를 한 번 끝까지 실행하고
    # 다시 부르기는 learning.
    # 마감 기준안 15분(learning→ai 대기 16분 안). 텍스트 시험에서 글 단계만 6~13분이라
    # 마감까지 남은 시간이 부족하면 다음 재생성을 시작하지 않음(ai.md 15절)
    theme_draft_deadline: float = 900.0
    # 테마 생성·검토 모델은 테마 전용 설정(사용자 결정 2026-11-10). 로컬·운영 OPENAI_MODEL이
    # gpt-6.1-terra라 기존 클라이언트를 쓰면 생성 = 검토가 되고 생성 비용이 약 10배.
    # 텍스트 시험은 생성 luna·검토 terra로 검증. 같은 OpenAI 키를 쓰고, 둘이 같으면 테마 경로만 503
    theme_generation_model: str = "gpt-6-luna"
    theme_review_model: str = "gpt-6.1-terra"
    # 호출 1번 상한(기준안). 줄거리 1회 실측 130~170초(2026-11-11, 출력 약 1만 토큰)에 180초로는
    # 시간 초과가 나서(repo-fair4-4) 300초로 올림. 전체는 theme_draft_deadline이 막음
    theme_llm_timeout: float = 300.0
    theme_llm_retries: int = 0  # 재시도 대신 그래프의 실패 사유 넣은 다시 생성
    theme_max_regen: int = 2  # 단계마다 다시 생성 상한(기준안, 첫 생성 포함 최대 3회)
    # 줄거리 검사가 칸 하나만 고치면 되는 사유로만 실패하면 줄거리 전체 대신 그 칸만 고쳐 쓰는
    # 상한(기준안). 줄거리 다시 생성 횟수와 따로 셈
    theme_max_text_fix: int = 2
    theme_review_max_rerun: int = 2  # 글 검토 뒤 다시 만들고 재검토하는 상한(기준안)
    # 마감까지 이보다 적게 남으면 다시 생성을 시작하지 않음(기준안)
    theme_min_regen_seconds: float = 180.0
    # 테마 미션 질문 글자 수 상한(기준안, 사용자 결정 2026-11-11, P19 확인 필요).
    # 테마 미션은 다룰 글·작품·대화·자료를 문제 글에 넣어야 해서 미션 초안 기준안 200자로는
    # 자주 넘음(실측 11번)
    theme_question_max_chars: dict[int, int] = {3: 400, 4: 400, 5: 400, 6: 400}
    theme_plan_max_tokens: int = 32000  # 줄거리·검토는 추론 출력이 길어 넉넉히(시험 최대 약 11,500)
    theme_review_max_tokens: int = 32000
    theme_dialogue_max_tokens: int = 8000
    # 지식 검색(#470) 연결 자리. 꺼져 있으면 요청의 성취기준으로 지금 틀대로 동작
    theme_knowledge_enabled: bool = False

    # 테마 그림·영상(#437, 사용자 결정 2026-11-10·11). 그림은 OpenAI(같은 키), 2D 만화풍.
    # 버킷(ASSET_S3_BUCKET, learning과 같은 버킷)이 비면 그림·영상·움직임을 건너뛰고 경고만
    image_provider: Literal["openai", "fake"] = "openai"
    image_model: str = "gpt-image-2.6-sunburst"
    image_size: str = "1536x864"  # 16:9 바로 생성(공식 크기 조건 안)
    image_quality: str = "medium"
    theme_image_timeout: float = 280.0  # 그림 1장 상한(기준안, 실측 약 30초)
    # 영상은 시작·종료만(컷 4개). 운영 Google 인증(기준안 WIF)이 정해질 때까지 기본 꺼짐.
    # 로컬은 gcloud로 받은 접근 토큰을 VIDEO_ACCESS_TOKEN에 넣어 시험(출력·커밋 금지)
    theme_video_enabled: bool = False
    video_provider: Literal["veo", "fake"] = "veo"
    video_model: str = "veo-3.1-fast-generate-001"
    video_project: str | None = None
    video_location: str = "us-central1"
    video_access_token: SecretStr | None = None
    theme_video_timeout: float = 400.0  # 컷 1개 생성·대기 상한(기준안, 실측 약 115초)
    # 시작·종료 영상 컷 길이(초, 컷 4개). 첫 그림만 고정하고 0.5초씩 겹쳐 녹아들게 이음
    # (사용자 결정 2026-11-11, 4+6+8+6-1.5 = 22.5초)
    theme_video_cut_seconds: list[int] = [4, 6, 8, 6]
    theme_motion_max_tokens: int = 8000  # 움직임 출력(기준안, 대화와 같은 값)
    asset_s3_bucket: str | None = None
    s3_endpoint_url: str | None = None  # 로컬 MinIO만, 비면 AWS S3
    s3_region: str = "ap-northeast-2"

    # 리포트 설명 sLLM (#477, FN-RPT-09). 클러스터 안 설명 전용 OpenAI 호환 서버(#476)이며
    # 다른 호출의 LLM 제공자(llm_provider)와 별개.
    # 주소가 비어 있으면 설명만 503(report는 설명 미포함)
    explanation_base_url: str | None = None
    explanation_model: str = "report-explanation"  # sLLM 서버에 올린 모델 이름(요청 model 값)
    explanation_api_key: str | None = None  # 클러스터 안 서버는 비워도 됨
    # 기준안: CPU 양자화 모델 실측(#475) 전 임시값. 답변 1개 = 항목 최대 2회 생성, 재시도 없음.
    # 주 1회 배치라 기다리는 사람이 없어 P12 예외. report→ai 대기(#479)는 마감보다 길게 잡음
    explanation_llm_timeout: float = 60.0
    explanation_deadline: float = 125.0
    explanation_max_tokens: int = 256

    # 분석 대화 전체 마감(초). core 기준 전체 120초(P12)보다 짧게, LLM 호출은 이 안에서만
    analysis_deadline: float = 110.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
