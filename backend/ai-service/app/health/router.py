"""liveness는 프로세스, readiness는 브로커·백그라운드 버전 조정 상태."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "UP"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    checks = {name: await check() for name, check in request.app.state.readiness_checks.items()}
    up = all(checks.values())
    return JSONResponse(
        {
            "status": "UP" if up else "DOWN",
            "checks": {name: "UP" if ok else "DOWN" for name, ok in checks.items()},
        },
        status_code=200 if up else 503,
    )
