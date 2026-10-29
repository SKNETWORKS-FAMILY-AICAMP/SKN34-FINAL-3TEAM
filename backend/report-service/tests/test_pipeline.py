import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from app.generation.pipeline import NamedGenerator, StudentDisplayName
from app.generation.records import RecordContractError
from app.security import UserContext, bind_user_context, reset_user_context
from tests.report_helpers import EmptyGenerator, command_for


class Names:
    def __init__(self, profile=None, error=None):
        self.profile, self.error, self.calls = profile, error, 0

    async def lookup(self, student_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.profile


class Capture(EmptyGenerator):
    async def generate(self, command, report):
        self.command = command
        return await super().generate(command, report)


def invoke(provider, previous, command, role="SYSTEM", scope=None):
    reset = bind_user_context(
        UserContext(None, role, frozenset(scope or [str(command.student_id)]))
    )
    try:
        return asyncio.run(NamedGenerator(provider, previous).generate(command, None))
    finally:
        reset_user_context(reset)


def test_resolved_name_overrides_untrusted_command_without_mutation():
    command = replace(command_for(uuid4()), display_name="untrusted")
    provider = Names(StudentDisplayName(command.student_id, "합성별명"))
    previous = Capture()
    invoke(provider, previous, command)
    assert provider.calls == previous.calls == 1
    assert previous.command.display_name == "합성별명"
    assert command.display_name == "untrusted"


@pytest.mark.parametrize("fault", ["wrong-student", "blank", "missing", "outage"])
def test_bad_name_or_lookup_failure_stops_before_records_ai_and_storage(fault):
    command, previous = command_for(uuid4()), Capture()
    provider = Names(StudentDisplayName(command.student_id, "합성별명"))
    if fault == "wrong-student":
        provider.profile = StudentDisplayName(uuid4(), "합성별명")
    elif fault in {"blank", "missing"}:
        provider.profile = StudentDisplayName(command.student_id, " " if fault == "blank" else None)
    else:
        provider.error = RuntimeError("synthetic outage")
    with pytest.raises((RecordContractError, RuntimeError)):
        invoke(provider, previous, command)
    assert previous.calls == 0


def test_parent_context_cannot_use_worker_name_lookup():
    command, previous = command_for(uuid4()), Capture()
    provider = Names(StudentDisplayName(command.student_id, "합성별명"))
    with pytest.raises(RecordContractError):
        invoke(provider, previous, command, role="PARENT")
    assert provider.calls == previous.calls == 0


def test_scope_checked_before_provider():
    from app.errors import ApiError

    command, previous = command_for(uuid4()), Capture()
    provider = Names(StudentDisplayName(command.student_id, "합성별명"))
    with pytest.raises(ApiError):
        invoke(provider, previous, command, scope=[str(uuid4())])
    assert provider.calls == previous.calls == 0
