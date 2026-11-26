import asyncio
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.generation.pipeline import NamedGenerator
from app.generation.records import RecordContractError
from app.security import UserContext, bind_user_context, reset_user_context
from tests.report_helpers import EmptyGenerator, command_for


class Capture(EmptyGenerator):
    async def generate(self, command, report):
        self.command = command
        return await super().generate(command, report)


def call(handler, previous=None, **changes):
    command = replace(command_for(uuid4()), **changes)
    previous = previous or EmptyGenerator()

    async def run():
        token = bind_user_context(UserContext(None, "SYSTEM", frozenset([str(command.student_id)])))
        try:
            async with internal_client(
                "http://core", transport=httpx.MockTransport(handler)
            ) as http:
                await NamedGenerator(CoreClient(http), previous).generate(command, None)
        finally:
            reset_user_context(token)

    return command, previous, run


def test_profile_uses_scoped_internal_headers():
    def handler(request):
        assert request.url.path in {
            f"/internal/students/{command.student_id}/profile",
            f"/internal/students/{command.student_id}/report-template",
        }
        assert request.headers["X-Internal-Token"]
        assert request.headers["X-User-Role"] == "SYSTEM"
        assert request.headers["X-Student-Scope"] == str(command.student_id)
        if request.url.path.endswith("/report-template"):
            return httpx.Response(200, json={"settings": {}, "revision": 0})
        return httpx.Response(200, json={"studentId": str(command.student_id), "nickname": "학생"})

    command, previous, run = call(handler)
    asyncio.run(run())
    assert previous.calls == 1


@pytest.mark.parametrize("fault", [403, 404, 500, "timeout", "wrong-id", "blank", "malformed"])
def test_profile_failure_never_retries_or_calls_downstream(fault):
    requests = []

    def handler(request):
        requests.append(request)
        if isinstance(fault, int):
            return httpx.Response(fault)
        if fault == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        if fault == "malformed":
            return httpx.Response(200, json={})
        return httpx.Response(
            200,
            json={
                "studentId": str(uuid4() if fault == "wrong-id" else command.student_id),
                "nickname": " " if fault == "blank" else "학생",
            },
        )

    command, previous, run = call(handler)
    with pytest.raises((httpx.HTTPError, RecordContractError, KeyError)):
        asyncio.run(run())
    assert len(requests) == 1 and previous.calls == 0


@pytest.mark.parametrize(
    "extra", [{}, {"parentSharingEnabled": False}, {"parentSharingEnabled": "legacy"}]
)
def test_weekly_generation_ignores_profile_sharing_field(extra):
    # #1064: 원문은 보호자 필수 동의로 제공된다. core #1061 전(옛 필드)·후(필드 없음) 모두 같다.
    def handler(request):
        if request.url.path.endswith("/report-template"):
            return httpx.Response(200, json={"settings": {}, "revision": 0})
        body = {"studentId": str(command.student_id), "nickname": "학생", **extra}
        return httpx.Response(200, json=body)

    capture = Capture()
    command, _, run = call(handler, capture, narrative_enabled=True)
    asyncio.run(run())
    assert capture.calls == 1
    assert capture.command.narrative_enabled is True
    assert capture.command.explanation_enabled is True
    assert not hasattr(capture.command, "parent_sharing_enabled")
