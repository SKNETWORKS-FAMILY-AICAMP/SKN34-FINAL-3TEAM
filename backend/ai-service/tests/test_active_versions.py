"""본문·버전 일치, scope 제한, 진행 중 요청의 선택 고정."""

import asyncio
import json
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.analysis_agent.models import AnalysisRequest
from app.analysis_agent.prompts import Classification
from app.analysis_agent.router import _events, get_record_tools
from app.analysis_agent.state import AgentContext
from app.bootstrap import create_app
from app.config import Settings
from app.errors import ApiError
from app.followup import prompts as followup_prompts
from app.followup.service import FollowupService
from app.judgment import prompts as judgment_prompts
from app.judgment.extractor import Extraction
from app.judgment.service import JudgmentService
from app.llm.providers import get_llm
from app.messaging.consumer import ModelVersionConsumer
from app.report_narrative import prompts as narrative_prompts
from app.report_narrative.models import NarrativeRequest
from app.report_narrative.service import NarrativeService
from app.versions import BUILTIN_PROMPTS, PROMPT_SCOPES, ActiveVersionItem, ActiveVersions
from tests.analysis_agent.records_fixture import FakeRecords
from tests.analysis_agent.test_router import BODY as ANALYSIS_BODY
from tests.fakes import FakeLlm
from tests.followup.test_service import make_request as followup_request
from tests.judgment.test_service import make_request as judgment_request
from tests.report_narrative.test_service import BODY as NARRATIVE_BODY


def version(name: str, release: str, revision: int = 1, scopes: list[str] | None = None):
    return ActiveVersionItem.model_validate(
        {
            "id": str(uuid4()),
            "kind": "PROMPT",
            "name": name,
            "version": release,
            "refId": None,
            "artifactUri": None,
            "scopes": scopes or [PROMPT_SCOPES[name]],
            "revision": revision,
            "activatedAt": datetime.now(UTC).isoformat(),
        }
    )


def installed(name: str, release: str) -> ActiveVersions:
    """향후 이미지에 두 번째 본문이 함께 들어간 상태를 모의한다."""
    source = BUILTIN_PROMPTS[name]
    alternate = ModuleType(f"{name}_alternate")
    alternate.PROMPT_VERSION = release
    for attr in (
        "SYSTEM",
        "CLASSIFY_SYSTEM",
        "ANSWER_SYSTEM",
        "build_user",
        "build_classify_user",
        "build_answer_user",
    ):
        if hasattr(source, attr):
            setattr(alternate, attr, getattr(source, attr))
    for attr in ("SYSTEM", "CLASSIFY_SYSTEM", "ANSWER_SYSTEM"):
        if hasattr(alternate, attr):
            setattr(alternate, attr, f"alternate {name}: " + getattr(alternate, attr))
    return ActiveVersions({name: {source.PROMPT_VERSION: source, release: alternate}})


def test_scope_revision_and_unknown_body() -> None:
    versions = ActiveVersions()
    name = "judgment"
    baseline = judgment_prompts.PROMPT_VERSION
    versions.replace([version(name, "judge@future", scopes=["ai/other"])])
    assert versions.prompt(name).version == baseline
    versions.apply(version(name, "judge@future", 2))
    with pytest.raises(ApiError) as error:
        versions.prompt(name)
    assert error.value.code == "AI_PROMPT_VERSION_UNAVAILABLE"
    assert not versions.is_ready()
    versions.apply(version(name, baseline, 1))
    assert not versions.is_ready()  # 오래된 revision은 무시
    versions.apply(version(name, baseline, 3, scopes=["ai/other"]))
    assert versions.prompt(name).version == baseline
    assert versions.is_ready()
    versions.replace([])
    assert versions.is_ready()


def test_all_four_functions_use_selected_body_and_report_its_version() -> None:
    async def run() -> None:
        settings = Settings(internal_token="test-token")

        versions = installed("judgment", "judge@next")
        versions.apply(version("judgment", "judge@next"))
        llm = FakeLlm(
            Extraction.model_validate(
                {
                    "elements": [
                        {"elementId": "e1", "status": "FOUND", "quote": "나는 찬성해"},
                        {"elementId": "e2", "status": "NOT_FOUND", "quote": None},
                    ]
                }
            )
        )
        judged = await JudgmentService(llm, settings, versions).judge(judgment_request())
        assert judged.versions.prompt == llm.requests[0].prompt_version == "judge@next"
        assert llm.requests[0].system.startswith("alternate judgment:")

        versions = installed("followup", "followup@next")
        versions.apply(version("followup", "followup@next"))
        llm = FakeLlm(
            followup_prompts.GeneratedQuestion(question="그렇게 생각한 까닭을 말해 줄래?")
        )
        followup = await FollowupService(llm, settings, versions).create(followup_request())
        assert followup.versions.prompt == llm.requests[0].prompt_version == "followup@next"
        assert llm.requests[0].system.startswith("alternate followup:")

        versions = installed("reportNarrative", "report@next")
        versions.apply(version("reportNarrative", "report@next"))
        llm = FakeLlm(
            narrative_prompts.GeneratedNarrative(
                narrative="기록을 살펴봤어요.", evening_question="무엇이 기억나?", cited_quotes=[]
            )
        )
        narrative = await NarrativeService(llm, settings, versions).generate(
            NarrativeRequest.model_validate(NARRATIVE_BODY)
        )
        assert narrative.versions.prompt == llm.requests[0].prompt_version == "report@next"
        assert llm.requests[0].system.startswith("alternate reportNarrative:")

        versions = installed("analysis", "analysis@next")
        versions.apply(version("analysis", "analysis@next"))
        llm = FakeLlm(
            Classification(intent="CHANGES", scope_issue="NONE"),
            "3개 시도 중 1개에서 되묻기 뒤에 답을 다시 썼어요. "
            "“왜냐하면 쉬는 시간이 길면”이라는 까닭을 더했어요.",
        )
        context = AgentContext(
            llm=llm,
            tools=FakeRecords(),
            deadline=asyncio.get_running_loop().time() + 60,
            prompt=versions.prompt("analysis"),
        )
        response = [
            event async for event in _events(AnalysisRequest.model_validate(ANALYSIS_BODY), context)
        ]
        assert any('"prompt": "analysis@next"' in event for event in response)
        assert [request.prompt_version for request in llm.requests] == [
            "analysis@next",
            "analysis@next",
        ]
        assert llm.requests[0].system.startswith("alternate analysis:")
        assert llm.requests[1].system.startswith("alternate analysis:")

    asyncio.run(run())


def test_prompt_selection_stays_fixed_during_request() -> None:
    async def run() -> None:
        versions = installed("judgment", "judge@next")
        llm = FakeLlm(
            Extraction.model_validate(
                {
                    "elements": [
                        {"elementId": "e1", "status": "NOT_FOUND", "quote": None},
                        {"elementId": "e2", "status": "NOT_FOUND", "quote": None},
                    ]
                }
            ),
            delay=0.02,
        )
        service = JudgmentService(llm, Settings(internal_token="test-token"), versions)
        task = asyncio.create_task(service.judge(judgment_request()))
        while not llm.requests:
            await asyncio.sleep(0)
        versions.apply(version("judgment", "judge@next"))
        response = await task
        assert response.versions.prompt == judgment_prompts.PROMPT_VERSION
        assert llm.requests[0].prompt_version == judgment_prompts.PROMPT_VERSION
        assert versions.prompt("judgment").version == "judge@next"

    asyncio.run(run())


def test_unknown_active_version_is_explicit_http_error_and_not_ready() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.active_versions.apply(version("judgment", "judge@unknown"))
        headers = {"X-Internal-Token": "test-token"}
        response = client.get("/internal/versions", headers=headers)
        assert response.status_code == 503
        assert response.json()["code"] == "AI_PROMPT_VERSION_UNAVAILABLE"
        from tests.judgment.test_router import BODY as JUDGMENT_BODY

        judged = client.post("/internal/judgments", json=JUDGMENT_BODY, headers=headers)
        assert judged.status_code == 503
        assert judged.json()["code"] == "AI_PROMPT_VERSION_UNAVAILABLE"
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json()["checks"]["versions"] == "DOWN"


def test_event_changes_subsequent_http_prompt_and_versions_endpoint() -> None:
    from tests.judgment.test_router import BODY as JUDGMENT_BODY

    llm = FakeLlm(
        Extraction.model_validate(
            {
                "elements": [
                    {"elementId": "e1", "status": "FOUND", "quote": "나는 찬성해"},
                ]
            }
        )
    )
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    with TestClient(app) as client:
        registry = installed("judgment", "judge@next")
        app.state.active_versions = registry
        consumer = ModelVersionConsumer(None, None, registry)
        consumer._initialized = True
        data = version("judgment", "judge@next", 2).model_dump(mode="json", by_alias=True)
        data["previousVersionId"] = None
        payload = {
            "id": str(uuid4()),
            "specversion": "1.0",
            "type": "model.version.activated",
            "source": "core-service",
            "time": datetime.now(UTC).isoformat(),
            "dataschema": "model.version.activated.v1",
            "data": data,
        }
        incoming = SimpleNamespace(body=json.dumps(payload).encode(), ack=AsyncMock())
        asyncio.run(consumer.receive(incoming))
        incoming.ack.assert_awaited_once()
        headers = {"X-Internal-Token": "test-token"}
        judged = client.post("/internal/judgments", json=JUDGMENT_BODY, headers=headers)
        active = client.get("/internal/versions", headers=headers)
    assert judged.status_code == 200
    assert judged.json()["versions"]["prompt"] == "judge@next"
    assert llm.requests[0].system.startswith("alternate judgment:")
    assert active.json()["prompts"]["judgment"] == "judge@next"


def test_unknown_analysis_prompt_closes_prepared_record_client() -> None:
    records = FakeRecords()
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: FakeLlm()
    app.dependency_overrides[get_record_tools] = lambda: records
    with TestClient(app) as client:
        app.state.active_versions.apply(version("analysis", "analysis@unknown"))
        response = client.post(
            "/internal/analysis/stream",
            json=ANALYSIS_BODY,
            headers={"X-Internal-Token": "test-token", "X-Student-Scope": "s-1"},
        )
    assert response.status_code == 503
    assert response.json()["code"] == "AI_PROMPT_VERSION_UNAVAILABLE"
    assert records.closed
