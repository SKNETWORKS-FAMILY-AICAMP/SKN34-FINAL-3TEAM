"""지식 임베딩 (#467, api-spec 4.2.4 계약 C6).

입력은 교육과정 지식 본문과 검색 질의 문장만 받는다(학생 정보·학생 답 없음).
contracts.Embedder를 만족해 ai 안의 검색 클라이언트(#470)도 같은 객체를 쓴다.
"""

from app.errors import ApiError
from app.knowledge.contracts import EmbeddingResponse
from app.llm.base import LlmUnavailable
from app.llm.embeddings import EmbeddingClient


class EmbeddingService:
    def __init__(self, client: EmbeddingClient) -> None:
        self._client = client

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        try:
            result = await self._client.embed(texts)
        except LlmUnavailable as exc:
            if exc.code == "LLM_INVALID_OUTPUT":
                raise ApiError(
                    502, "AI_BAD_RESPONSE", "임베딩 응답 형식 오류", retryable=True
                ) from exc
            raise ApiError(503, "AI_UNAVAILABLE", "AI 처리 실패", retryable=exc.retryable) from exc
        return EmbeddingResponse(
            model=result.model, dimensions=result.dimensions, vectors=result.vectors
        )
