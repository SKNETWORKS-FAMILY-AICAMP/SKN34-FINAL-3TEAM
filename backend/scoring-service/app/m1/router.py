"""M2와 동일한 내부 인증·컨텍스트 의존성을 사용한다."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.m1.models import M1Inactive, M1Request
from app.security import UserContext, get_user_context

router = APIRouter(prefix="/internal/m1")


@router.post("/checks", response_model=M1Inactive)
async def check(
    body: M1Request,
    request: Request,
    context: Annotated[UserContext, Depends(get_user_context)],
):
    return await request.app.state.m1_service.check(body)
