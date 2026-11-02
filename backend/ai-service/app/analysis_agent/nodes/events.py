"""노드가 진행 중에 보내는 사용자 정의 스트림 조각. 라우터가 SSE 이벤트로 바꿈."""

from typing import Any


def status(message: str) -> dict[str, Any]:
    return {"event": "status", "data": {"state": "RUNNING", "message": message}}


def delta(text: str) -> dict[str, Any]:
    """대조 전 임시 답변 조각. 확정 답변은 result로만 (API 3.3)."""
    return {"event": "delta", "data": {"text": text}}
