import time

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.theme_draft.models import ThemeDraftRequest, ThemeDraftResponse, ThemeFailureResult
from app.theme_draft.router import get_theme_draft_runner
from tests.theme_draft.helpers import mission_body, request_body, sample_response

HEADERS = {"X-Internal-Token": "test-token"}
INTERNAL_THEME_FIELDS = {"features", "target", "clueType", "condition", "evidence"}


class FakeRunner:
    def __init__(self, response: ThemeDraftResponse | None = None) -> None:
        self.response = response or sample_response()
        self.calls: list[tuple[ThemeDraftRequest, float]] = []

    async def run(self, request: ThemeDraftRequest, deadline: float) -> ThemeDraftResponse:
        self.calls.append((request, deadline))
        return self.response


def post(body: dict, runner: FakeRunner | None = None, headers: dict[str, str] = HEADERS):
    app = create_app()
    if runner is not None:
        app.dependency_overrides[get_theme_draft_runner] = lambda: runner
    with TestClient(app) as client:
        return client.post("/internal/theme-drafts", json=body, headers=headers)


def test_response_uses_contract_fields_only() -> None:
    response = post(request_body(), FakeRunner())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "theme",
        "missions",
        "dialogues",
        "images",
        "videos",
        "motions",
        "warnings",
        "failure",
        "versions",
    }
    theme = body["theme"]
    assert set(theme) == {
        "title",
        "world",
        "characters",
        "styleNote",
        "outfit",
        "intro",
        "outro",
        "bigQuestion",
        "candidates",
        "answer",
        "days",
    }
    assert set(theme["days"][0]) == {
        "day",
        "thinkingType",
        "place",
        "sceneNote",
        "clue",
        "rulesOut",
    }
    assert not INTERNAL_THEME_FIELDS & (
        set(theme) | set(theme["days"][0])
    )  # 정답 논리 검사용 내부 칸은 응답에 없음
    assert body["missions"][0]["day"] == "MON" and set(body["missions"][0]["draft"]) >= {
        "question",
        "hints",
        "elements",
    }
    assert body["versions"] == {"model": "fake-model", "prompt": "theme-draft@1"}


def test_service_passes_deadline_from_settings() -> None:
    runner = FakeRunner()
    started = time.monotonic()
    post(request_body(), runner)
    ((request, deadline),) = runner.calls
    assert request.grade == 3 and request.mission_for("SOLVE").input_type == "SOLUTION_STEPS"
    assert 899 <= deadline - started <= 901  # 기준안 15분


def test_missing_internal_token_is_401() -> None:
    assert post(request_body(), FakeRunner(), headers={}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        request_body(gradeMax=4),  # 학년별 테마라 두 값이 같아야 함
        request_body(
            missions=[mission_body(t) for t in ("ANALYZE", "EVALUATE", "CREATE", "SOLVE")]
        ),  # 5개가 아님
        request_body(
            missions=[mission_body(t) for t in ("ANALYZE", "ANALYZE", "CREATE", "SOLVE", "REFLECT")]
        ),  # 유형 중복
        request_body(
            missions=[{**mission_body("EVALUATE"), "inputType": "ESSAY"}]
            + [mission_body(t) for t in ("ANALYZE", "CREATE", "SOLVE", "REFLECT")]
        ),  # 초3 논술
        request_body(previousFailures=[{"stage": "AI_CALL", "reasons": ["TIMEOUT"]}]),  # 네 값 밖
        request_body(
            previousFailures=[{"stage": "LEARNING", "reasons": ["MON ELEMENT_CODE"]}]
        ),  # 네 값 밖
        request_body(previousFailures=[{"stage": "MISSION", "reasons": []}]),  # 사유 없음
        request_body(gradeMin=2, gradeMax=2),
    ],
)
def test_bad_request_is_400(body: dict) -> None:
    response = post(body, FakeRunner())
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_previous_failures_four_stages_accepted() -> None:
    failures = [
        {"stage": s, "reasons": ["MON ELEMENT_CODE rubric.elements.code"]}
        for s in ("THEME", "MISSION", "REVIEW", "IMAGE")
    ]
    runner = FakeRunner()
    assert post(request_body(previousFailures=failures), runner).status_code == 200
    assert [f.stage for f in runner.calls[0][0].previous_failures] == [
        "THEME",
        "MISSION",
        "REVIEW",
        "IMAGE",
    ]


def test_essay_allowed_from_grade_five() -> None:
    missions = [{**mission_body("EVALUATE"), "inputType": "ESSAY"}] + [
        mission_body(t) for t in ("ANALYZE", "CREATE", "SOLVE", "REFLECT")
    ]
    assert post(request_body(grade=5, missions=missions), FakeRunner()).status_code == 200


def test_runner_not_ready_is_503_not_retryable() -> None:
    response = post(request_body())  # 그래프가 붙기 전 기본 구현
    assert response.status_code == 503
    assert response.json()["code"] == "AI_UNAVAILABLE" and response.json()["retryable"] is False


def test_failure_response_allows_missing_theme() -> None:
    # 줄거리 단계에서 끝내 실패하면 쓸 수 있는 테마가 없어 theme은 null, learning은 CHECK_FAILED
    failed = sample_response().model_copy(
        update={
            "theme": None,
            "missions": [],
            "dialogues": [],
            "failure": ThemeFailureResult(stage="THEME", reasons=["LOGIC MON HINT"]),
        }
    )
    body = post(request_body(), FakeRunner(failed)).json()
    assert body["theme"] is None and body["failure"] == {
        "stage": "THEME",
        "reasons": ["LOGIC MON HINT"],
    }
