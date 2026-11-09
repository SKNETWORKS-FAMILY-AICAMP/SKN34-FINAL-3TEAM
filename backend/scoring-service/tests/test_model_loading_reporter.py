import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from app.model_loading_reporter import ModelLoadingReporter
from app.model_registry import ModelRegistry
from tests.test_model_registry import loaded, version


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_two_replicas_failure_retains_previous_and_reports_only_error_type():
    ok = ModelRegistry(loaded)
    fail = ModelRegistry(loaded)
    await fail.load(version(1))

    def broken(v):
        raise ValueError("secret s3://credential/path")

    fail._loader = broken
    await ok.load(version(2))
    with pytest.raises(ValueError):
        await fail.load(version(2))
    p1, p2 = AsyncMock(), AsyncMock()
    a, b = ModelLoadingReporter(ok, p1), ModelLoadingReporter(fail, p2)
    await a.publish()
    await b.publish()
    good = p1.publish.call_args.args[0].data
    bad = p2.publish.call_args.args[0].data
    assert good["instanceId"] != bad["instanceId"]
    assert good["models"][0]["status"] == "LOADED"
    m = bad["models"][0]
    assert m["status"] == "FAILED" and m["errorType"] == "ValueError"
    assert m["previousModelRetained"] and m["loadedRevision"] == 1
    assert "secret" not in str(bad)
    await b.publish()
    assert p2.publish.call_args.args[0].data["sequence"] == 2


@pytest.mark.anyio
async def test_heartbeat_empty_snapshot_and_failure_do_not_break_loading():
    registry = ModelRegistry(loaded)
    publisher = AsyncMock()
    publisher.publish.side_effect = TimeoutError()
    reporter = ModelLoadingReporter(registry, publisher)
    await reporter.publish()
    await registry.load(version())
    await registry.replace([])
    await reporter.publish()
    assert publisher.publish.call_args.args[0].data["models"] == []


@pytest.mark.anyio
async def test_actual_payloads_match_model_loading_event_contract():
    # 가상 예시가 아니라 reporter가 실제로 보내는 LOADED·FAILED·빈 data를 계약으로 검사한다.
    path = Path(__file__).resolve().parents[3] / "contracts/events"
    schema = json.loads(
        (path / "model.loading.reported.v1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    registry = ModelRegistry(loaded)
    publisher = AsyncMock()
    reporter = ModelLoadingReporter(registry, publisher)
    await reporter.publish()
    await registry.load(version(1))
    await reporter.publish()

    def broken(v):
        raise ValueError("secret s3://credential/path")

    registry._loader = broken
    with pytest.raises(ValueError):
        await registry.load(version(2))
    await reporter.publish()
    payloads = [call.args[0].data for call in publisher.publish.call_args_list]
    assert [[m["status"] for m in p["models"]] for p in payloads] == [[], ["LOADED"], ["FAILED"]]
    for payload in payloads:
        validator.validate(payload)
