"""내부 인증은 공통 미들웨어, 컨텍스트는 공통 의존성에서 전달받는다."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.m2.models import M2Active, M2Inactive, M2Request
from app.security import UserContext, get_user_context

router = APIRouter(prefix="/internal/m2")


@router.post("/scores", response_model=M2Active | M2Inactive)
async def score(
    body: M2Request,
    request: Request,
    context: Annotated[UserContext, Depends(get_user_context)],
):
    # 학생 ID가 없는 채점 API. 권한 컨텍스트를 원문·사용량 이벤트에 넣지 않는다.
    return await request.app.state.m2_service.score(body)
