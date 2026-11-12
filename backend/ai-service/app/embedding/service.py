"""지식 임베딩 (#467, api-spec 4.2.4 계약 C6).

입력은 교육과정 지식 본문·검색 질의(purpose KNOWLEDGE)와 추억 검색 문서·학생 질문
(purpose MEMORY, P27 #565). 학생 이름·ID는 받지 않고 원문은 로그에 남기지 않는다.
contracts.Embedder를 만족해 ai 안의 검색 클라이언트(#470)도 같은 객체를 쓴다
(purpose 생략 = KNOWLEDGE).
"""

from app.errors import ApiError
from app.knowledge.contracts import EmbeddingPurpose, EmbeddingResponse
from app.llm.base import LlmUnavailable
from app.llm.embeddings import EmbeddingClient


class EmbeddingService:
    def __init__(self, client: EmbeddingClient) -> None:
        self._client = client

    async def embed(
        self, texts: list[str], purpose: EmbeddingPurpose = "KNOWLEDGE"
    ) -> EmbeddingResponse:
        try:
            result = await self._client.embed(texts, purpose)
        except LlmUnavailable as exc:
            if exc.code == "LLM_INVALID_OUTPUT":
                raise ApiError(
                    502, "AI_BAD_RESPONSE", "임베딩 응답 형식 오류", retryable=True
                ) from exc
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc
        return EmbeddingResponse(
            model=result.model, dimensions=result.dimensions, vectors=result.vectors
        )
