from typing import Annotated

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import security
from app.bootstrap import create_app
from app.security import UserContext, caller_permits, get_user_context

probe = APIRouter()
PRIVATE_TEXT = "PRIVATE-STUDENT-TEXT"


class ProbeCount(BaseModel):
    count: int


@probe.get("/internal/m2/probe/invalid-response", response_model=ProbeCount)
async def probe_invalid_response() -> dict[str, str]:
    return {"count": PRIVATE_TEXT}


@probe.get("/internal/m2/probe/invalid-model")
async def probe_invalid_model() -> ProbeCount:
    return ProbeCount.model_validate({"count": PRIVATE_TEXT})


@probe.get("/internal/m2/probe/students/{student_id}")
async def probe_student(
    student_id: str, context: Annotated[UserContext, Depends(get_user_context)]
) -> dict[str, str | None]:
    context.require_student(student_id)
    return {"userId": context.user_id}


def make_client() -> TestClient:
    app = create_app()
    app.include_router(probe)
    return TestClient(app)


def test_live() -> None:
    with make_client() as client:
        assert client.get("/health/live").json() == {"status": "UP"}


def test_ready_down_without_dependencies() -> None:
    with make_client() as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["rabbitmq"] == "DOWN"


def test_internal_without_token_is_401_problem() -> None:
    with make_client() as client:
        response = client.get("/internal/m2/probe/students/s1")
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_internal_context_and_scope() -> None:
    headers = {"X-Internal-Token": "test-token", "X-User-Id": "p1", "X-Student-Scope": "s1,s2"}
    with make_client() as client:
        ok = client.get("/internal/m2/probe/students/s1", headers=headers)
        forbidden = client.get("/internal/m2/probe/students/s9", headers=headers)
    assert ok.json() == {"userId": "p1"}
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"


def test_not_found_uses_traceparent() -> None:
    headers = {
        "X-Internal-Token": "test-token",
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    }
    with make_client() as client:
        body = client.get("/internal/m2/unknown", headers=headers).json()
    assert body["code"] == "NOT_FOUND"
    assert body["traceId"] == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_valid_token_outside_allowlist_is_403() -> None:
    with make_client() as client:
        response = client.get("/internal/not-allowed", headers={"X-Internal-Token": "test-token"})
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "FORBIDDEN"


def test_caller_tokens_are_separate(monkeypatch) -> None:
    base = security.get_settings()
    blank = {"internal_token_" + c.replace("-", "_"): "" for c in security.CALLER_PATHS}
    blank["internal_token_ai"] = "caller-token"
    monkeypatch.setattr(security, "get_settings", lambda: base.model_copy(update=blank))
    headers = {"X-Internal-Token": "caller-token", "X-Student-Scope": "s1"}
    with make_client() as client:
        ok = client.get("/internal/m2/probe/students/s1", headers=headers)
        stale = client.get(
            "/internal/m2/probe/students/s1", headers={"X-Internal-Token": "test-token"}
        )
        empty = client.get("/internal/m2/probe/students/s1", headers={"X-Internal-Token": ""})
        other = client.get(
            "/internal/models/preflight", headers={"X-Internal-Token": "caller-token"}
        )
    assert other.status_code == 403
    assert ok.status_code == 200
    assert stale.status_code == 401
    assert empty.status_code == 401


def test_dot_segments_never_match_allowlist() -> None:
    assert caller_permits("ai", "/internal/m2/probe/students/s1")
    assert not caller_permits("ai", "/internal/m2/probe/../../not-allowed")


@pytest.mark.parametrize("path", ["invalid-response", "invalid-model"])
def test_validation_error_does_not_log_input(path, caplog) -> None:
    headers = {"X-Internal-Token": "test-token", "X-Student-Scope": "s1"}
    with make_client() as client:
        response = client.get(f"/internal/m2/probe/{path}", headers=headers)
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "응답 스키마 검증 실패" in caplog.text
    assert PRIVATE_TEXT not in caplog.text + response.text
