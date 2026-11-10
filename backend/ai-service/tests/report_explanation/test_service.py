import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.config import Settings
from app.errors import ApiError
from app.llm.base import LlmError
from app.prompt_versions.models import ActiveVersionItem
from app.prompt_versions.registry import ActiveVersions
from app.prompt_versions.service import PromptSync
from app.report_explanation.models import (
    ActiveExplanationResponse,
    ExplanationRequest,
    InactiveExplanationResponse,
)
from app.report_explanation.service import ExplanationService
from tests.fakes import FakeLlm
from tests.report_explanation.test_checks import NARRATIVE

TEXT = "나는 강아지를 키우고 싶다. 왜냐하면 강아지는 산책을 좋아해서 운동이 된다."
BODY = {"grade": 5, "inputType": "NARRATIVE", "text": TEXT, "scores": NARRATIVE}


def model_item(
    scopes: list[str], kind: str = "MODEL", name: str = "report-explanation"
) -> ActiveVersionItem:
    return ActiveVersionItem.model_validate(
        {
            "id": str(uuid4()),
            "kind": kind,
            "name": name,
            "version": "lora-1",
            "refId": None,
            "artifactUri": "s3://models/report-explanation/lora-1/" if kind == "MODEL" else None,
            "scopes": scopes,
            "revision": 1,
            "activatedAt": datetime.now(UTC).isoformat(),
        }
    )


def active(*scopes: str) -> ActiveVersions:
    versions = ActiveVersions()
    versions.replace([model_item(list(scopes))])
    return versions


def service(llm: FakeLlm, versions: ActiveVersions | None = None) -> ExplanationService:
    return ExplanationService(llm, Settings(), versions or active("explanation/grade-5/narrative"))


def explain(llm: FakeLlm, body: dict = BODY, versions: ActiveVersions | None = None):
    return asyncio.run(service(llm, versions).explain(ExplanationRequest.model_validate(body)))


def test_two_items_become_parent_text_with_quote_and_registry_version() -> None:
    llm = FakeLlm(
        "강아지가 산책으로 운동이 된다는 까닭을 구체적으로 들었음. 그래서 5점.",
        "앞 문장과 뒤 문장을 잇는 말이 부족함.",
    )
    result = explain(llm)
    assert isinstance(result, ActiveExplanationResponse)
    assert result.explanation.text == (
        "잘한 점: 강아지가 산책으로 운동이 된다는 까닭을 구체적으로 들었음.\n"
        "함께 이야기해 볼 점: 앞 문장과 뒤 문장을 잇는 말이 부족함."
    )
    assert result.explanation.quote == "왜냐하면 강아지는 산책을 좋아해서 운동이 된다."
    assert result.versions.model_dump() == {
        "model": "report-explanation@lora-1",
        "prompt": "report-explanation@1",
    }
    assert [r.user.splitlines()[0] for r in llm.requests] == [
        "[학년] 초5 [항목] 구체성 [점수] 5",
        "[학년] 초5 [항목] 연결성 [점수] 2",
    ]
    assert all(r.user.endswith(TEXT) for r in llm.requests)
    assert {u.call_type for u in llm.usages} == {"REPORT_EXPLANATION"}


@pytest.mark.parametrize(
    "versions",
    [
        ActiveVersions(),  # 설명 모델 미등록
        active("explanation/grade-6/narrative"),  # 다른 학년만 승인
        active("explanation/grade-5/essay"),  # 다른 입력 유형만 승인
    ],
)
def test_inactive_or_out_of_scope_model_answers_inactive_without_calling_llm(
    versions: ActiveVersions,
) -> None:
    llm = FakeLlm()
    assert isinstance(explain(llm, versions=versions), InactiveExplanationResponse)
    assert llm.requests == []


def test_prompt_with_same_name_does_not_activate_model() -> None:
    versions = ActiveVersions()
    versions.replace([model_item(["explanation/grade-5/narrative"], kind="PROMPT")])
    assert isinstance(explain(FakeLlm(), versions=versions), InactiveExplanationResponse)


def test_item_left_empty_after_cleaning_is_422_not_retryable() -> None:
    llm = FakeLlm("까닭을 들었음.", "3점짜리 글임. 점수가 낮음.")
    with pytest.raises(ApiError) as error:
        explain(llm)
    assert (error.value.status, error.value.code) == (422, "AI_EXPLANATION_REJECTED")
    assert error.value.extra == {"retryable": False}


def test_llm_failure_is_503() -> None:
    llm = FakeLlm(LlmError("LLM_SERVER_ERROR", retryable=True))
    with pytest.raises(ApiError) as error:
        explain(llm)
    assert (error.value.status, error.value.code) == (503, "AI_UNAVAILABLE")


def test_model_activation_follows_revision_and_reaches_pending_sync() -> None:
    versions = active("explanation/grade-5/narrative")
    narrowed = model_item(["explanation/grade-6/narrative"]).model_copy(update={"revision": 2})
    versions.apply(narrowed)
    assert versions.model("report-explanation", "explanation/grade-5/narrative") is None
    assert versions.model("report-explanation", "explanation/grade-6/narrative") == narrowed
    versions.apply(model_item(["explanation/grade-5/narrative"]))  # 오래된 revision은 무시
    assert versions.model("report-explanation", "explanation/grade-5/narrative") is None
    assert versions.is_ready()  # 모델 유무는 프롬프트 준비 상태와 무관


def test_prompt_sync_keeps_model_event_received_before_snapshot() -> None:
    class Core:
        async def active_versions(self) -> list[ActiveVersionItem]:
            return []

    versions = ActiveVersions()
    sync = PromptSync(Core(), versions)  # type: ignore[arg-type]
    sync.offer(model_item(["explanation/grade-5/narrative"]))
    sync.offer(model_item(["explanation/grade-5/narrative"], name="m2-klue-narrative"))
    asyncio.run(sync.synchronize(asyncio.Event()))
    assert versions.model("report-explanation", "explanation/grade-5/narrative") is not None
    assert versions.model("m2-klue-narrative", "explanation/grade-5/narrative") is None
