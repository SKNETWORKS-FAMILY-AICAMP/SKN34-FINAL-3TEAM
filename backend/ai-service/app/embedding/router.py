from typing import Annotated

from fastapi import APIRouter, Depends

from app.embedding.service import EmbeddingService
from app.knowledge.contracts import EmbeddingRequest, EmbeddingResponse
from app.llm.embeddings import EmbeddingClient, get_embedder

router = APIRouter(prefix="/internal/embeddings", tags=["embedding"])


def get_embedding_service(
    client: Annotated[EmbeddingClient, Depends(get_embedder)],
) -> EmbeddingService:
    return EmbeddingService(client)


@router.post("", response_model=EmbeddingResponse)
async def create_embeddings(
    body: EmbeddingRequest,
    service: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> EmbeddingResponse:
    return await service.embed(body.texts)
