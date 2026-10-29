"""노드가 진행 중에 보내는 사용자 정의 스트림 조각. 라우터가 SSE status 이벤트로 바꿈."""

from typing import Any


def status(message: str) -> dict[str, Any]:
    return {"event": "status", "data": {"state": "RUNNING", "message": message}}
