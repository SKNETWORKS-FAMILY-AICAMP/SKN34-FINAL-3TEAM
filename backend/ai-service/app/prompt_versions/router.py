"""ai가 현재 사용하는 프롬프트 버전 내부 조회."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/internal/versions", tags=["versions"])


@router.get("")
async def versions(request: Request) -> dict[str, dict[str, str]]:
    return {"prompts": request.app.state.active_versions.active_prompt_versions()}
