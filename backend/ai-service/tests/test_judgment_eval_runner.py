"""#199 판정 평가 러너 (evaluation/runners/judgment_eval.py) 단위 테스트. 대역 LLM만 사용."""

import argparse
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.judgment.extractor import Extraction
from app.llm.base import LlmError
from app.llm.providers import get_llm
from tests.fakes import FakeLlm

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "judgment_eval", ROOT / "evaluation" / "runners" / "judgment_eval.py"
)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

CASES = ROOT / "evaluation" / "datasets" / "judgment" / "cases.example.jsonl"


def found(*pairs: tuple[str, str | None]) -> Extraction:
    return Extraction.model_validate(
        {
            "elements": [
                {"elementId": eid, "status": "FOUND" if q else "NOT_FOUND", "quote": q}
                for eid, q in pairs
            ]
        }
    )


def client_judge(llm: FakeLlm):
    """러너의 judge 자리에 실제 라우터(/internal/judgments)를 대역 LLM으로 연결."""
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: llm
    client = TestClient(app)
    client.__enter__()

    def judge(body: dict) -> dict:
        response = client.post(
            "/internal/judgments", json=body, headers={"X-Internal-Token": "test-token"}
        )
        response.raise_for_status()
        return response.json()

    return judge


def args(tmp_path: Path, **extra) -> argparse.Namespace:
    base = [
        "--cases", str(CASES),
        "--dataset-id", "judgment-example",
        "--dataset-version", "0",
        "--human-review", "테스트",
        "--out-dir", str(tmp_path),
    ]  # fmt: skip
    for key, value in extra.items():
        base += [f"--{key.replace('_', '-')}", str(value)]
    return runner.parse_args(base)


# 예시 4건 대역 응답: ex-01 주장·까닭 충족(CORRECT), ex-02 인용 불일치(HELD),
# ex-03 바뀐 생각만(PARTIAL), ex-04는 너무 짧아 LLM 호출 없이 HELD
LLM_STEPS = (
    found(
        ("e1", "나는 쉬는 시간을 늘리는 데 찬성해"),
        ("e2", "수업에 더 집중할 수 있어"),
        ("e3", None),
    ),
    found(("e1", "나는 반대야"), ("e2", "없는 문장"), ("e3", None)),
    found(("e1", "처음에는 물이 그냥 사라진다고 생각했는데"), ("e2", None)),
)


def test_qwk_known_values() -> None:
    assert runner.qwk([0, 1, 2, 2], [0, 1, 2, 2], 3) == 1.0
    assert runner.qwk([0, 0, 1, 1], [1, 1, 0, 0], 2) == -1.0
    assert runner.qwk([1, 1, 1], [1, 1, 1], 2) is None  # 한 범주뿐이면 정의 안 됨
    assert runner.qwk([0], [0], 3) is None


def test_load_cases_rejects_missing_rater_mark(tmp_path: Path) -> None:
    case = json.loads(CASES.read_text(encoding="utf-8").splitlines()[0])
    del case["raters"]["r2"]["e3"]
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="r2"):
        runner.load_cases(bad)


def test_run_reports_agreement_held_and_registry_evaluation(tmp_path: Path) -> None:
    report, evaluation = runner.run(args(tmp_path), client_judge(FakeLlm(*LLM_STEPS)))
    summary = json.loads(report.read_text(encoding="utf-8"))
    o = summary["overall"]

    assert (summary["prompt"], summary["model"]) == ("judge@2", "fake-model")
    assert o["cases"] == 4 and o["callErrors"] == 0
    assert o["held"] == 2 and o["heldReasons"] == {"QUOTE_MISMATCH": 1, "TOO_SHORT": 1}
    assert o["heldRatio"] == 0.5
    assert o["quoteMismatchRatio"] == round(1 / 3, 3)  # LLM 호출 3건 중 1건
    # 사람끼리: ex-02의 e2만 다름 → 요소 10개 중 9개 일치
    assert o["humanHuman"]["elementAgreement"] == 0.9
    # 사람-AI: 판정된 ex-01·ex-03만 비교, ex-03 e2(사람 충족·AI 미충족)만 다름
    assert o["humanAi"]["judgedCases"] == 2
    assert o["humanAi"]["elementAgreement"] == 0.8
    assert set(summary["scopes"]) == {"judgment/grade-5/essay", "judgment/grade-4/narrative"}
    assert set(summary["missions"]) == {"m-ex-essay", "m-ex-narr"}
    assert summary["missions"]["m-ex-essay"]["held"] == 1
    # 요소별: 논술 e2(까닭)는 ex-02에서 사람끼리 다름, 서술 e2는 ex-03에서 AI만 다름
    elements = summary["elements"]
    assert elements["m-ex-essay/e2"]["humanHumanAgreement"] == 0.5
    assert elements["m-ex-essay/e2"]["judgedCases"] == 1  # ex-02는 보류라 사람-AI에서 빠짐
    assert elements["m-ex-narr/e2"] == {
        "cases": 2,
        "judgedCases": 1,
        "humanHumanAgreement": 1.0,
        "humanAiAgreement": 0.0,
    }
    assert "answerText" not in report.read_text(encoding="utf-8")  # 원문 미저장

    ev = json.loads(evaluation.read_text(encoding="utf-8"))
    assert set(ev) == {
        "datasetId", "datasetVersion", "baselineVersion", "comparisonReport",
        "trainingEvaluationSeparation", "quoteAccuracy", "calculationAccuracy",
        "humanReview", "evaluatedScopes",
    }  # fmt: skip
    assert all(isinstance(v, str) and v for k, v in ev.items() if k != "evaluatedScopes")
    assert ev["evaluatedScopes"] == ["judgment/grade-4/narrative", "judgment/grade-5/essay"]


def test_compare_with_baseline_and_call_error_counted(tmp_path: Path) -> None:
    first, _ = runner.run(args(tmp_path / "a"), client_judge(FakeLlm(*LLM_STEPS)))
    # 두 번째 실행: 첫 사례 LLM 실패(503) → callErrors 1
    steps = (LlmError("down", retryable=True), *LLM_STEPS[1:])
    report, evaluation = runner.run(
        args(tmp_path / "b", baseline=first), client_judge(FakeLlm(*steps))
    )
    summary = json.loads(report.read_text(encoding="utf-8"))
    assert summary["overall"]["callErrors"] == 1
    assert summary["comparison"]["baseline"] == "judge@2 / fake-model"
    assert summary["comparison"]["overall"]["callErrors"] == 1
    ev = json.loads(evaluation.read_text(encoding="utf-8"))
    assert ev["baselineVersion"] == "judge@2/fake-model"
