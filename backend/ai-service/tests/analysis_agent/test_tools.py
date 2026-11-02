import asyncio

import httpx
import pytest

from app.analysis_agent.tools import RecordTools
from app.clients import learning_client as learning_module
from app.clients.learning_client import LearningClient, RecordsUnavailable
from app.security import UserContext
from tests.analysis_agent.records_fixture import PERIOD, SCOPE, summary

USER = UserContext(user_id="p-1", role="PARENT", student_scope=frozenset({"s-1"}))
OUTSIDER = UserContext(user_id="p-2", role="PARENT", student_scope=frozenset({"s-9"}))
TOOL_CALLS = {
    "summary": lambda tools: tools.summary(SCOPE),
    "thinking_types": lambda tools: tools.thinking_types(SCOPE),
    "attempts": lambda tools: tools.attempts(SCOPE, 8),
    "changes": lambda tools: tools.changes(SCOPE),
    "thinking_activities": lambda tools: tools.thinking_activities(SCOPE),
    "evidence": lambda tools: tools.evidence(SCOPE, ["a-1"]),
}


def use_transport(monkeypatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        learning_module,
        "internal_client",
        lambda base_url: httpx.AsyncClient(
            base_url=base_url, transport=httpx.MockTransport(recording)
        ),
    )
    return seen


async def run(user: UserContext, call):
    tools = RecordTools(LearningClient("http://learning", user), user)
    try:
        return await call(tools)
    finally:
        await tools.aclose()


@pytest.mark.parametrize("name", TOOL_CALLS)
def test_every_tool_rechecks_permission_before_learning(monkeypatch, name) -> None:
    seen = use_transport(monkeypatch, lambda request: httpx.Response(200, json={}))
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(run(OUTSIDER, TOOL_CALLS[name]))
    assert (caught.value.code, caught.value.retryable) == ("FORBIDDEN", False)
    assert seen == []  # 권한 밖이면 learning을 호출하지 않음


def test_summary_without_record_count_is_invalid(monkeypatch) -> None:
    response = {"studentId": "s-1", "state": "OK", "period": PERIOD, "metrics": summary()[1:]}
    use_transport(monkeypatch, lambda request: httpx.Response(200, json=response))
    with pytest.raises(RecordsUnavailable) as caught:
        asyncio.run(run(USER, lambda tools: tools.summary(SCOPE)))
    assert caught.value.code == "RECORDS_INVALID"
