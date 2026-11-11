"""지식 RAG 계약의 ai 쪽 모델과 인터페이스 (#464 계약 C5·C6·C7, api-spec 4.1.2·4.2.4·4.2.5).

- C5: learning 지식 내부 API(`/internal/knowledge/...`) 요청·응답.
  learning이 구현(#469)하고 ai가 부름(#470)
- C6: ai 임베딩 API(`/internal/embeddings`) 요청·응답. ai가 구현(#467)하고 learning·스크립트가 부름
- C7: 미션 초안 요청의 근거 칸(`knowledge` = C5 standards 응답 그대로)과 응답 `sources`
- 검색 클라이언트 인터페이스(`KnowledgeRetriever`)는 #470 `retriever.py`가 구현한다

JSON 필드는 camelCase(ApiModel). 학생 정보는 어떤 모델에도 없다.
값 옆 "기준안"은 팀 확인 전 값이다(api-spec 4.1.2 기준안 표).
"""

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from pydantic import ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.followup.models import ThinkingType
from app.judgment.models import ApiModel

# ---- C6 임베딩 (기준안: 에픽 #463 결정 요약·#467)
EMBEDDING_MODEL = "text-embedding-3-small"  # 기준안
EMBEDDING_DIMENSIONS = 1536  # 기준안
EMBEDDING_MAX_TEXTS = 64  # 기준안: 한 요청 본문 개수 상한
EMBEDDING_MAX_CHARS = 8000  # 기준안: 본문 하나 글자 수 상한

# ---- C5 지식 API 상한·기본값 (기준안)
STANDARDS_MAX_CODES = 10
SEARCH_DEFAULT_K = 5
SEARCH_MAX_K = 20
THEME_DEFAULT_K = 3
THEME_MAX_K = 10
LEARNED_MAX_CONCEPTS = 20
DEFAULT_MIN_SIMILARITY = 0.7  # 에픽 기준안(결과서 양식 예시 값), 실측 후 조정

KnowledgeKind = Literal["STANDARD", "DOMAIN", "CONTENT", "SUBJECT_GUIDE", "THINKING_TYPE"]
Subject = Literal["국어", "도덕", "사회", "수학", "과학"]
DomainScope = Literal["BOTH", "CONTENT_SYSTEM", "STANDARD_GROUP"]
ContentCategory = Literal["K", "P", "V"]
# learning이 200 응답에 담는 대체 사유(근거 없음). 오류(4xx·5xx)와 구분한다
FallbackReason = Literal[
    "NO_ACTIVE_DATASET", "BELOW_THRESHOLD", "NO_CANDIDATE", "CODE_NOT_FOUND", "NO_REVIEWED_RELATION"
]
# ai 검색 클라이언트가 근거 없이 생성할 때 남기는 사유 = learning 사유 + 호출 쪽 사유
RetrievalFallback = Literal[
    "NO_ACTIVE_DATASET",
    "BELOW_THRESHOLD",
    "NO_CANDIDATE",
    "CODE_NOT_FOUND",
    "NO_REVIEWED_RELATION",
    "KNOWLEDGE_UNAVAILABLE",  # learning 지식 API 5xx·연결 실패·계약 밖 응답
    "KNOWLEDGE_TIMEOUT",  # 시간 상한 초과
    "KNOWLEDGE_DISABLED",  # 기능 스위치 꺼짐
]
Verdict = Literal["LEARNED", "NOT_YET", "HOLD"]
Grade = Annotated[int, Field(ge=3, le=6)]
Semester = Annotated[str, Field(pattern=r"^[3-6]-[12]$")]
Similarity = Annotated[float, Field(ge=0.0, le=1.0)]
Vector = Annotated[list[float], Field(min_length=1)]


# ---- C5·C7 공통: 근거 표시
class KnowledgeRef(ApiModel):
    """근거 조각 표시 `{kind, id, datasetVersion}`. C5 응답 조각마다 붙고 C7 `sources` 항목."""

    kind: KnowledgeKind
    id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)


class ContentItem(ApiModel):
    group: str | None
    text: str


class StandardView(ApiModel):
    code: str
    subject: Subject
    grades: list[int]
    semesters: list[str]
    notice_grade_band: str
    area: str
    statement: str
    explanation: str | None
    ref: KnowledgeRef


class DomainView(ApiModel):
    id: str
    subject: Subject
    area: str
    scope: DomainScope
    core_ideas: list[str]
    knowledge: list[ContentItem]
    process: list[ContentItem]
    values: list[ContentItem]
    considerations: list[str]
    activities: list[str]
    ref: KnowledgeRef


class ContentView(ApiModel):
    id: str
    domain_id: str
    category: ContentCategory
    group: str | None
    text: str
    ref: KnowledgeRef


class FitView(ApiModel):
    thinking_type: ThinkingType
    reason: str


class StandardBundle(ApiModel):
    """성취기준 하나의 근거 묶음.

    사회·과학은 domain이 단원(고려 사항)이고 내용 체계 항목은 covers로 이어진다.
    """

    standard: StandardView
    domain: DomainView | None
    covers: list[ContentView]
    fits: list[FitView]
    grade_match: bool | None  # grade를 주면 그 학년에 배우는 성취기준인지, 안 주면 null


class SubjectGuideView(ApiModel):
    subject: Subject
    teaching: list[str]
    assessment: list[str]
    ref: KnowledgeRef


class ThinkingTypeBasis(ApiModel):
    framework: str
    attribution: str


class ThinkingTypeElement(ApiModel):
    code: str
    label: str
    description: str


class ThinkingTypeGuide(ApiModel):
    """생각 유형 출제 지침. 팀이 우리 말로 쓴 지침과 출처 표기만(블룸·VALUE 원문 없음)."""

    type: ThinkingType
    name: str
    basis: list[ThinkingTypeBasis]
    elements: list[ThinkingTypeElement]
    question_must: list[str]
    question_must_not: list[str]
    ref: KnowledgeRef


class KnowledgeBundle(ApiModel):
    """`GET /internal/knowledge/standards` 200 응답. C7 미션 초안 요청 `knowledge` 칸 그대로."""

    dataset_version: str | None
    items: list[StandardBundle]
    missing_codes: list[str]
    subject_guides: list[SubjectGuideView]
    thinking_type: ThinkingTypeGuide | None
    reason: FallbackReason | None


class ThinkingTypeResponse(ApiModel):
    dataset_version: str | None
    guide: ThinkingTypeGuide | None
    reason: FallbackReason | None


class SearchFilters(ApiModel):
    """빈 배열은 거르지 않음. 칸 안은 OR, 칸끼리는 AND, grades·semesters는 겹치면 통과."""

    kinds: list[KnowledgeKind] = Field(default_factory=list)
    subjects: list[Subject] = Field(default_factory=list)
    grades: list[Grade] = Field(default_factory=list)
    semesters: list[Semester] = Field(default_factory=list)
    thinking_types: list[ThinkingType] = Field(default_factory=list)


class SearchRequest(ApiModel):
    vector: Vector
    embedding_model: str = Field(min_length=1)
    k: int = Field(default=SEARCH_DEFAULT_K, ge=1, le=SEARCH_MAX_K)
    min_similarity: Similarity = DEFAULT_MIN_SIMILARITY
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SearchHit(ApiModel):
    ref: KnowledgeRef
    kind: KnowledgeKind
    subject: Subject | None
    area: str | None
    standard_code: str | None
    domain_id: str | None
    thinking_type: ThinkingType | None
    grades: list[int]
    semesters: list[str]
    text: str
    similarity: Similarity


class SearchResponse(ApiModel):
    dataset_version: str | None
    items: list[SearchHit]
    reason: FallbackReason | None


class ThemeCandidatesRequest(ApiModel):
    vector: Vector
    embedding_model: str = Field(min_length=1)
    grade: Grade
    semester: Semester
    k: int = Field(default=THEME_DEFAULT_K, ge=1, le=THEME_MAX_K)
    min_similarity: Similarity = DEFAULT_MIN_SIMILARITY


class ThemeCandidate(ApiModel):
    code: str
    statement: str
    subject: Subject
    area: str
    similarity: Similarity
    matched_by: KnowledgeRef  # 주제와 비슷했던 조각(성취기준 또는 내용 요소)
    fit_reason: str
    ref: KnowledgeRef


class ThemeTypeCandidates(ApiModel):
    thinking_type: ThinkingType
    candidates: list[ThemeCandidate]
    reason: FallbackReason | None


class ThemeCandidatesResponse(ApiModel):
    dataset_version: str | None
    grade: int
    semester: str
    types: list[ThemeTypeCandidates]  # 다섯 유형 모두, 후보 없는 유형은 빈 목록과 사유
    reason: FallbackReason | None


class LearnedConcept(ApiModel):
    text: str = Field(min_length=1)
    vector: Vector


class LearnedRequest(ApiModel):
    concepts: list[LearnedConcept] = Field(min_length=1, max_length=LEARNED_MAX_CONCEPTS)
    embedding_model: str = Field(min_length=1)
    grade: Grade
    semester: Semester
    min_similarity: Similarity = DEFAULT_MIN_SIMILARITY


class LearnedMatch(ApiModel):
    content_id: str
    text: str
    similarity: Similarity
    ref: KnowledgeRef


class LearnedIn(ApiModel):
    standard_code: str
    semester: str


class LearnedItem(ApiModel):
    text: str
    verdict: Verdict
    matched: LearnedMatch | None
    learned_in: list[LearnedIn]
    reason: FallbackReason | None  # HOLD일 때 BELOW_THRESHOLD 또는 NO_REVIEWED_RELATION


class LearnedResponse(ApiModel):
    dataset_version: str | None
    grade: int
    semester: str
    items: list[LearnedItem]
    reason: FallbackReason | None


# ---- C6
class EmbeddingRequest(ApiModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    texts: list[Annotated[str, Field(min_length=1, max_length=EMBEDDING_MAX_CHARS)]] = Field(
        min_length=1, max_length=EMBEDDING_MAX_TEXTS
    )

    @field_validator("texts")
    @classmethod
    def _no_blank_text(cls, texts: list[str]) -> list[str]:
        """공백만인 글은 빈 글과 같이 400 (api-spec 4.2.4)."""
        if any(not text.strip() for text in texts):
            raise ValueError("texts 항목은 공백만일 수 없음")
        return texts


class EmbeddingResponse(ApiModel):
    model: str
    dimensions: int
    vectors: list[list[float]]  # 요청 texts와 같은 순서·같은 개수


# ---- 검색 클라이언트 결과와 인터페이스
@dataclass(frozen=True)
class RetrievalResult[T]:
    """근거가 있으면 value, 근거 없이 기존 방식으로 생성해야 하면 fallback(사유)."""

    value: T | None
    fallback: RetrievalFallback | None


def sources_of(bundle: KnowledgeBundle) -> list[KnowledgeRef]:
    """C7 응답 `sources`: 프롬프트에 넣은 근거 묶음의 조각 표시(중복 없이 나온 순서대로)."""
    refs: list[KnowledgeRef] = []
    for item in bundle.items:
        refs.append(item.standard.ref)
        if item.domain is not None:
            refs.append(item.domain.ref)
        refs.extend(content.ref for content in item.covers)
    refs.extend(guide.ref for guide in bundle.subject_guides)
    if bundle.thinking_type is not None:
        refs.append(bundle.thinking_type.ref)
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for ref in refs:
        key = (ref.kind, ref.id, ref.dataset_version)
        if key not in seen:
            seen.add(key)
            unique.append(ref)
    return unique


class Embedder(Protocol):
    """C6 임베딩. ai 안에서는 #467 `embedding.service.EmbeddingService`(app.state.embedder로
    만든 것), 시험·개발에는 fake.FakeEmbedder."""

    async def embed(self, texts: list[str]) -> EmbeddingResponse: ...


class KnowledgeApi(Protocol):
    """C5 learning 지식 내부 API 클라이언트. 개발 중에는 fake.FakeKnowledgeApi를 감싸 쓴다."""

    async def standards(
        self, codes: list[str], grade: int | None, thinking_type: ThinkingType | None
    ) -> KnowledgeBundle: ...

    async def thinking_type(self, thinking_type: ThinkingType) -> ThinkingTypeResponse: ...

    async def search(self, request: SearchRequest) -> SearchResponse: ...

    async def theme_candidates(
        self, request: ThemeCandidatesRequest
    ) -> ThemeCandidatesResponse: ...

    async def learned(self, request: LearnedRequest) -> LearnedResponse: ...


class KnowledgeRetriever(Protocol):
    """생성 쪽이 쓰는 검색 클라이언트(#470 retriever.py가 구현).

    질의 임베딩(C6) → learning 지식 API(C5)를 묶고, 장애·시간 초과·근거 없음은 예외 대신
    RetrievalResult.fallback으로 돌려준다(생성은 근거 없이 기존 방식으로 계속).
    """

    async def mission_knowledge(
        self, codes: list[str], grade: int | None, thinking_type: ThinkingType
    ) -> RetrievalResult[KnowledgeBundle]: ...

    async def theme_candidates(
        self, topic: str, grade: int, semester: str
    ) -> RetrievalResult[ThemeCandidatesResponse]: ...

    async def check_learned(
        self, concepts: list[str], grade: int, semester: str
    ) -> RetrievalResult[LearnedResponse]: ...

    async def search(
        self, query: str, filters: SearchFilters, k: int
    ) -> RetrievalResult[SearchResponse]: ...
