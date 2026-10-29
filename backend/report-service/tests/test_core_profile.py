import asyncio
from uuid import uuid4

import httpx
import pytest

from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.generation.pipeline import NamedGenerator
from app.generation.records import RecordContractError
from app.security import UserContext, bind_user_context, reset_user_context
from tests.report_helpers import EmptyGenerator, command_for


def call(handler):
    command, previous = command_for(uuid4()), EmptyGenerator()

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
        assert request.url.path == f"/internal/students/{command.student_id}/profile"
        assert request.headers["X-Internal-Token"]
        assert request.headers["X-User-Role"] == "SYSTEM"
        assert request.headers["X-Student-Scope"] == str(command.student_id)
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
