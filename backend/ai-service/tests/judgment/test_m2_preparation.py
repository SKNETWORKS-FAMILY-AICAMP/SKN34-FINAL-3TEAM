"""#549 점수 없는 정리 결과는 판정·평균·보류에 참여하지 않는다."""

import pytest

from app.clients.scoring_client import M2Scores
from app.judgment.cross_check import m2_body
from tests.judgment.test_cross_check import MODEL, FakeScoring, judge, make_request


def payload():
    return {
        "active": True,
        "scored": False,
        "reason": "TEXT_TOO_SHORT",
        "inputType": "NARRATIVE",
        "model": MODEL,
        "preparation": {
            "copied": 1,
            "repeated": False,
            "chars": 3,
            "labelsRemoved": 0,
            "short": True,
            "notices": ["EMPTY_AFTER_CLEANING"],
        },
    }


def test_skipped_preserves_judgment_and_has_no_mean_or_scores():
    response = judge(FakeScoring(m2=M2Scores.model_validate(payload())))
    assert response.result == "CORRECT"
    assert response.held_reason is None
    assert response.model_scores.m2 is None
    assert response.model_scores.skipped is None
    wire = response.model_scores.model_dump(by_alias=True)
    assert wire["m2Preparation"]["notices"] == ["EMPTY_AFTER_CLEANING"]
    assert "mean" not in str(wire)


@pytest.mark.parametrize(
    "change", [{"reason": None}, {"preparation": None}, {"scores": {"org": 0}}, {"scored": True}]
)
def test_malformed_skip_is_rejected(change):
    with pytest.raises(ValueError):
        M2Scores.model_validate(payload() | change)


def test_custom_labels_are_forwarded_without_changing_original():
    labels = ["내 생각", "첫째", "둘째", "반대 생각"]
    request = make_request(inputType="ESSAY", essayType="주장", essayLabels=labels)
    body = m2_body(request)
    assert body["essayLabels"] == labels
    assert body["text"] == request.answer_text
