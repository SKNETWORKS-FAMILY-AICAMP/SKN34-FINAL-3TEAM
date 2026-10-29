"""미학습 계약·인증·입력·원문 비노출 회귀 검증."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.m1.models import M1Request
from app.m1.service import M1Service

BODY = {
    "problem": "비공개 문항: 2 더하기 3",
    "answerKey": "5",
    "solution": {"steps": ["", "비공개 풀이: 2+3=5"], "finalAnswer": "5"},
}
HEADERS = {"X-Internal-Token": "test-token"}


@pytest.fixture
def client():
    app = create_app()
    app.state.m1_service = M1Service()
    return TestClient(app)


@pytest.mark.parametrize("final_answer", ["5", "999", "1/2"])
def test_untrained_model_never_guesses_correctness(client, final_answer, caplog):
    body = deepcopy(BODY)
    body["solution"]["finalAnswer"] = final_answer
    response = client.post("/internal/m1/checks", json=body, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"active": False}
    assert "비공개" not in caplog.text


@pytest.mark.parametrize("headers", [{}, {"X-Internal-Token": "wrong"}])
def test_authentication(client, headers):
    assert client.post("/internal/m1/checks", json=BODY, headers=headers).status_code == 401


@pytest.mark.parametrize(
    "patch",
    [
        {"problem": None},
        {"problem": "  "},
        {"answerKey": 5},
        {"answerKey": "\n"},
        {"grade": 5},
        {"solution": "풀이"},
        {"solution": {"steps": [], "finalAnswer": "5"}},
        {"solution": {"steps": [" ", "\n"], "finalAnswer": "5"}},
        {"solution": {"steps": [5], "finalAnswer": "5"}},
        {"solution": {"steps": ["풀이"], "finalAnswer": " "}},
        {"solution": {"steps": ["풀이"], "finalAnswer": "5", "extra": 1}},
    ],
)
def test_invalid_inputs_are_400_without_echoing_raw_input(client, patch, caplog):
    response = client.post("/internal/m1/checks", json=BODY | patch, headers=HEADERS)
    assert response.status_code == 400
    assert "비공개" not in response.text + caplog.text


@pytest.mark.parametrize("missing", ["problem", "answerKey", "solution"])
def test_required_fields(client, missing):
    body = deepcopy(BODY)
    del body[missing]
    assert client.post("/internal/m1/checks", json=body, headers=HEADERS).status_code == 400


def test_student_step_indices_and_text_are_preserved():
    assert M1Request.model_validate(BODY).model_dump() == BODY


def test_malformed_json(client):
    response = client.post(
        "/internal/m1/checks", content="{", headers=HEADERS | {"Content-Type": "application/json"}
    )
    assert response.status_code == 400
