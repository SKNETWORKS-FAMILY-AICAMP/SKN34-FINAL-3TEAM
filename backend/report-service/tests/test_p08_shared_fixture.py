"""P08 rules checked against the fixture shared with learning and ai (#836, architecture 1.1)."""

import json
from pathlib import Path

import pytest

from app.clients.learning_client import AnswerInput
from app.generation.metrics import MIN_SAMPLE, REASON_CONNECTIVES, sample_state, text_counts

CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts/examples/p08-metrics/cases.json").read_text(
        encoding="utf-8"
    )
)


def test_connectives_and_sample_threshold_match_shared_fixture():
    assert list(REASON_CONNECTIVES) == CASES["reasonConnectives"]
    assert MIN_SAMPLE == CASES["minSample"]


@pytest.mark.parametrize("case", CASES["textCounts"], ids=lambda c: c["name"])
def test_written_text_counts_match_shared_fixture(case):
    answer = AnswerInput.model_construct(input_type=case["inputType"], content=case["content"])
    assert text_counts(answer.written_text()) == case["expected"]


@pytest.mark.parametrize("case", CASES["sampleState"], ids=lambda c: str(c["count"]))
def test_sample_state_matches_shared_fixture(case):
    assert sample_state(case["count"]) == case["state"]


@pytest.mark.parametrize(
    "case", CASES["ratio"], ids=lambda c: f"{c['numerator']}/{c['denominator']}"
)
def test_ratio_state_matches_shared_fixture(case):
    # Report ratios are shown only when the sample state is OK (MetricsCalculator).
    state = sample_state(case["denominator"])
    value = case["numerator"] / case["denominator"] if state == "OK" else None
    assert (value, state) == (case["value"], case["state"])
