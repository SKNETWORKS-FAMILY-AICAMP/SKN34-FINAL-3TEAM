"""learning 답변 제출에서 부르는 표현 분류. 내부 인증은 공통 미들웨어(learning만 허용)."""

from fastapi import APIRouter, Request

from app.toxicity.models import ToxicityActive, ToxicityInactive, ToxicityRequest

router = APIRouter(prefix="/internal/toxicity")


@router.post("/checks", response_model=ToxicityActive | ToxicityInactive)
async def check(body: ToxicityRequest, request: Request):
    return await request.app.state.toxicity_service.check(body)
