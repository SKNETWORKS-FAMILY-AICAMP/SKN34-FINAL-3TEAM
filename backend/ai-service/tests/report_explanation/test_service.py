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
    ExplanationDetail,
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


def detail(**changes) -> ExplanationDetail:
    values = {
        "analysis": "강아지가 산책을 좋아해서 운동이 된다는 까닭을 들어 주장을 펼쳤습니다.",
        "improvement_points": "다만, 키우고 싶은 까닭과 운동 이야기의 연결이 짧습니다.",
        "next_steps": "앞으로 '강아지와 산책하면 무엇이 좋을까?'라고 물어봐 주세요.",
    }
    return ExplanationDetail(**(values | changes))


def test_one_call_becomes_titled_detail_with_quote_and_registry_version() -> None:
    llm = FakeLlm(detail())
    result = explain(llm, {**BODY, "topic": "키우고 싶은 동물과 까닭을 써 보세요."})
    assert isinstance(result, ActiveExplanationResponse)
    assert result.explanation.text == (
        "상세 분석\n강아지가 산책을 좋아해서 운동이 된다는 까닭을 들어 주장을 펼쳤습니다.\n\n"
        "보완할 지점\n다만, 키우고 싶은 까닭과 운동 이야기의 연결이 짧습니다.\n\n"
        "개선 방안\n앞으로 '강아지와 산책하면 무엇이 좋을까?'라고 물어봐 주세요."
    )
    assert result.explanation.quote == "왜냐하면 강아지는 산책을 좋아해서 운동이 된다."
    assert result.versions.model_dump() == {
        "model": "report-explanation@lora-1",
        "prompt": "report-explanation@4",
    }
    [request] = llm.requests
    assert request.user.splitlines()[:3] == [
        "[학년] 초등 5학년",
        "[문제] 키우고 싶은 동물과 까닭을 써 보세요.",
        "[학생 글]",
    ]
    assert request.user.endswith(TEXT) and "4" not in request.user  # 점수는 넣지 않음
    assert {u.call_type for u in llm.usages} == {"REPORT_EXPLANATION"}


def test_scores_are_optional() -> None:
    body = {key: value for key, value in BODY.items() if key != "scores"}
    assert isinstance(explain(FakeLlm(detail()), body), ActiveExplanationResponse)


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


def test_analysis_left_empty_after_cleaning_is_422_after_one_regeneration() -> None:
    bad = detail(analysis="점수가 낮은 글입니다. 등급은 보통입니다.")
    llm = FakeLlm(bad, bad)
    with pytest.raises(ApiError) as error:
        explain(llm)
    assert (error.value.status, error.value.code) == (422, "AI_EXPLANATION_REJECTED")
    assert error.value.extra == {"retryable": False}
    assert [request.repetition_penalty for request in llm.requests] == [None, 1.1]


def test_repeated_sentences_trigger_one_regeneration_with_repetition_penalty() -> None:
    same = "필통의 색과 그림은 썼지만 그 물건이 왜 소중한지는 아직 드러나지 않습니다."
    looping = detail(analysis=same, improvement_points=same, next_steps=same)
    llm = FakeLlm(looping, detail())
    result = explain(llm)
    assert isinstance(result, ActiveExplanationResponse)
    assert "강아지가 산책을 좋아해서" in result.explanation.text
    assert [request.repetition_penalty for request in llm.requests] == [None, 1.1]


def test_a_single_repeat_is_dropped_without_regeneration() -> None:
    analysis = (
        "강아지가 산책을 좋아해서 운동이 된다는 까닭을 들어 주장을 펼쳤습니다. "
        "주장과 까닭이 바로 이어져 읽기 쉽습니다. 산책 이야기로 생활과 연결했습니다."
    )
    llm = FakeLlm(
        detail(
            analysis=analysis,
            improvement_points=(
                "다만, 키우고 싶은 까닭과 운동 이야기의 연결이 짧습니다. "
                "주장과 까닭이 바로 이어져 읽기 쉽습니다."
            ),
        )
    )
    result = explain(llm)
    assert isinstance(result, ActiveExplanationResponse)
    assert result.explanation.text.count("주장과 까닭이 바로 이어져 읽기 쉽습니다.") == 1
    assert len(llm.requests) == 1


def test_still_insufficient_after_regeneration_is_422() -> None:
    same = "필통의 색과 그림은 썼지만 그 물건이 왜 소중한지는 아직 드러나지 않습니다."
    looping = detail(analysis=same, improvement_points=same, next_steps=same)
    llm = FakeLlm(looping, looping)
    with pytest.raises(ApiError) as error:
        explain(llm)
    assert error.value.code == "AI_EXPLANATION_REJECTED"
    assert len(llm.requests) == 2


def test_bad_sentence_is_dropped_not_the_whole_explanation() -> None:
    llm = FakeLlm(detail(improvement_points="다만, 연결이 짧습니다. 점수가 낮은 글입니다."))
    result = explain(llm)
    assert isinstance(result, ActiveExplanationResponse)
    assert "보완할 지점\n다만, 연결이 짧습니다.\n\n" in result.explanation.text
    assert "점수" not in result.explanation.text


def test_invalid_output_regenerates_once_with_repetition_penalty() -> None:
    # 출력 한도까지 반복(LLM_INVALID_OUTPUT)이면 같은 작업 재접수가 아니라 설정을 바꿔 한 번만
    llm = FakeLlm(LlmError("LLM_INVALID_OUTPUT", retryable=True), detail())
    assert isinstance(explain(llm), ActiveExplanationResponse)
    assert [request.repetition_penalty for request in llm.requests] == [None, 1.1]


def test_invalid_output_twice_is_503_after_two_requests() -> None:
    error_step = LlmError("LLM_INVALID_OUTPUT", retryable=True)
    llm = FakeLlm(error_step, error_step)
    with pytest.raises(ApiError) as error:
        explain(llm)
    assert error.value.code == "AI_UNAVAILABLE"
    assert len(llm.requests) == 2


def test_timeout_is_not_regenerated() -> None:
    llm = FakeLlm(LlmError("LLM_TIMEOUT", retryable=True), detail())
    with pytest.raises(ApiError) as error:
        explain(llm)
    assert error.value.code == "AI_UNAVAILABLE"
    assert len(llm.requests) == 1


def test_llm_failure_is_503() -> None:
    llm = FakeLlm(*[LlmError("LLM_SERVER_ERROR", retryable=True)] * 2)
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


def test_local_skip_registry_calls_llm_without_active_model(monkeypatch) -> None:
    llm = FakeLlm(detail())
    monkeypatch.setenv("EXPLANATION_LOCAL_SKIP_REGISTRY", "1")
    result = explain(llm, versions=ActiveVersions())
    assert isinstance(result, ActiveExplanationResponse)
    assert result.versions.model == "gemma-4-26b-a4b-it-qat-awq-int4@local-unregistered"
    monkeypatch.setenv("EXPLANATION_LOCAL_SKIP_REGISTRY", "true")  # 정확히 "1"만 켬
    assert isinstance(explain(FakeLlm(), versions=ActiveVersions()), InactiveExplanationResponse)
