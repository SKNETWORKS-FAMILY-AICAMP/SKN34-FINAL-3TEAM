"""P08 표본 규칙을 learning·report와 같은 공통 픽스처로 검사 (#836, architecture 1.1).

글자·문장·까닭을 잇는 말 수는 ai가 세지 않고 learning 값을 그대로 쓰므로 표본 규칙만 본다.
"""

import json
from pathlib import Path

import pytest

from app.analysis_agent.calculators import MIN_RATIO_DENOMINATOR, count_metric, ratio_metric
from app.analysis_agent.models import Period
from tests.analysis_agent.records_fixture import PERIOD

CASES = json.loads(
    (Path(__file__).resolve().parents[4] / "contracts/examples/p08-metrics/cases.json").read_text(
        encoding="utf-8"
    )
)
PERIOD_ = Period.model_validate(PERIOD)


def test_sample_threshold_matches_shared_fixture() -> None:
    assert MIN_RATIO_DENOMINATOR == CASES["minSample"]


@pytest.mark.parametrize("case", CASES["sampleState"], ids=lambda c: str(c["count"]))
def test_count_state_matches_shared_fixture(case) -> None:
    assert count_metric("건수", case["count"], "건수", PERIOD_).state == case["state"]


@pytest.mark.parametrize(
    "case", CASES["ratio"], ids=lambda c: f"{c['numerator']}/{c['denominator']}"
)
def test_ratio_matches_shared_fixture(case) -> None:
    metric = ratio_metric("비율", case["numerator"], case["denominator"], "분자 / 분모", PERIOD_)
    assert (metric.value, metric.state) == (case["value"], case["state"])
