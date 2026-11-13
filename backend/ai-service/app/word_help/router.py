from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.llm.base import LlmClient
from app.llm.providers import get_llm
from app.word_help.models import WordHelpRequest, WordHelpResponse
from app.word_help.service import WordHelpService

router = APIRouter(prefix="/internal/word-helps", tags=["word-help"])


def get_word_help_service(
    request: Request, llm: Annotated[LlmClient, Depends(get_llm)]
) -> WordHelpService:
    return WordHelpService(
        llm, request.app.state.dictionary, get_settings(), request.app.state.active_versions
    )


@router.post("", response_model=WordHelpResponse)
async def create_word_help(
    body: WordHelpRequest,
    service: Annotated[WordHelpService, Depends(get_word_help_service)],
) -> WordHelpResponse:
    return await service.help(body)
