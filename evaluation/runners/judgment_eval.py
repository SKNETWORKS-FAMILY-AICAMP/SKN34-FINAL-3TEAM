"""판정 품질 평가 러너 (#199, NFR-AIQ-01·05·06).

고정 평가 자료(cases.jsonl)의 답안마다 ai `/internal/judgments`를 호출하고,
평가자 2명의 요소별 표시와 비교해 사람-사람·사람-AI 일치도를 계산한다.

- 결과 일치도(QWK): 판정 결과를 RETHINK(0) < PARTIAL(1) < CORRECT(2)로 보고 계산.
  사람 결과는 평가자 요소 표시에 서비스와 같은 규칙(`app.judgment.service._result`)을 적용해 만든다.
- 요소 일치율·kappa: 요소마다 충족/미충족이 같은 비율과 Cohen kappa(2범주라 QWK와 같음).
- HELD는 사람-AI 일치도에서 빼고 보류 비율·사유로 따로 센다
  (보류를 낮은 수준으로 세지 않음, FN-JDG-04).
- 결과 요약은 학생 원문을 담지 않는다 (숫자·사유·버전만).

실행 (ai-service 가상환경, 서비스가 떠 있는 상태):
  cd backend/ai-service
  uv run python ../../evaluation/runners/judgment_eval.py \
    --cases ../../evaluation/datasets/judgment/cases.jsonl \
    --dataset-id judgment-p11 --dataset-version 1 \
    --base-url http://localhost:8000 --token "$INTERNAL_TOKEN" \
    --human-review "평가자 2명 독립 표시, 검토 기록: <링크>" \
    [--baseline ../../evaluation/results/judgment/<기준선>.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "ai-service"))

from app.judgment.models import JudgmentElement, RubricElement  # noqa: E402
from app.judgment.service import _result  # noqa: E402

RESULT_LEVEL = {"RETHINK": 0, "PARTIAL": 1, "CORRECT": 2}
RATERS = ("r1", "r2")
Judge = Callable[[dict], dict]


def load_cases(path: Path) -> list[dict]:
    cases = []
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        case = json.loads(line)
        ids = [e["elementId"] for e in case["rubric"]["elements"]]
        for rater in RATERS:
            marks = case["raters"][rater]
            if sorted(marks) != sorted(ids):
                raise ValueError(f"{path.name} {no}행: {rater} 표시 요소가 기준표 요소와 다름")
        cases.append(case)
    if not cases:
        raise ValueError(f"{path.name}: 평가 사례 없음")
    return cases


def scope_key(case: dict) -> str:
    """모델 레지스트리 범위 키 (api-spec 5.2 예: judgment/grade-3/narrative)."""
    return f"judgment/grade-{case['grade']}/{case['inputType'].lower()}"


def human_result(case: dict, rater: str) -> str:
    rubric = [RubricElement.model_validate(e) for e in case["rubric"]["elements"]]
    marks = case["raters"][rater]
    elements = [
        JudgmentElement(
            element_id=e.element_id, quote=None, verified=True, satisfied=marks[e.element_id]
        )
        for e in rubric
    ]
    return _result(rubric, elements)


def qwk(a: list[int], b: list[int], k: int) -> float | None:
    """quadratic weighted kappa. 값이 모두 한 범주라 기대 불일치가 0이면 None."""
    if len(a) != len(b) or len(a) < 2:
        return None
    n = len(a)
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        obs[x][y] += 1
    row = [sum(r) for r in obs]
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            num += w * obs[i][j]
            den += w * row[i] * col[j] / n
    return None if den == 0 else round(1 - num / den, 3)


def _rate(pairs: list[tuple[bool, bool]]) -> float | None:
    return round(sum(x == y for x, y in pairs) / len(pairs), 3) if pairs else None


def _mean(values: list[float | None]) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def summarize(rows: list[dict]) -> dict:
    """rows: 사례별 {case, response | None(호출 실패)} → 지표 묶음."""
    called = [r for r in rows if r["response"] is not None]
    held = [r for r in called if r["response"]["result"] == "HELD"]
    judged = [r for r in called if r["response"]["result"] != "HELD"]
    reasons = Counter(r["response"]["heldReason"] for r in held)
    llm_called = [
        r
        for r in called
        if r["response"].get("heldReason") not in ("TOO_SHORT", "UNVERIFIED_SCOPE")
    ]

    hh_result = qwk(
        [RESULT_LEVEL[human_result(r["case"], "r1")] for r in rows],
        [RESULT_LEVEL[human_result(r["case"], "r2")] for r in rows],
        3,
    )
    hh_elem = [
        (r["case"]["raters"]["r1"][eid], r["case"]["raters"]["r2"][eid])
        for r in rows
        for eid in r["case"]["raters"]["r1"]
    ]
    ha_result, ha_elem, ha_kappa = [], [], []
    for rater in RATERS:
        ha_result.append(
            qwk(
                [RESULT_LEVEL[human_result(r["case"], rater)] for r in judged],
                [RESULT_LEVEL[r["response"]["result"]] for r in judged],
                3,
            )
        )
        pairs = [
            (r["case"]["raters"][rater][e["elementId"]], e["satisfied"])
            for r in judged
            for e in r["response"]["elements"]
        ]
        ha_elem.append(_rate(pairs))
        ha_kappa.append(qwk([int(x) for x, _ in pairs], [int(y) for _, y in pairs], 2))

    return {
        "cases": len(rows),
        "callErrors": len(rows) - len(called),
        "held": len(held),
        "heldRatio": round(len(held) / len(called), 3) if called else None,
        "heldReasons": dict(sorted(reasons.items())),
        "quoteMismatchRatio": round(reasons.get("QUOTE_MISMATCH", 0) / len(llm_called), 3)
        if llm_called
        else None,
        "humanHuman": {
            "resultQwk": hh_result,
            "elementAgreement": _rate(hh_elem),
            "elementKappa": qwk([int(x) for x, _ in hh_elem], [int(y) for _, y in hh_elem], 2),
        },
        "humanAi": {
            "judgedCases": len(judged),
            "resultQwk": _mean(ha_result),
            "elementAgreement": _mean(ha_elem),
            "elementKappa": _mean(ha_kappa),
        },
    }


def evaluate(cases: list[dict], judge: Judge) -> dict:
    rows = []
    for case in cases:
        body = {
            "answerText": case["answerText"],
            "inputType": case["inputType"],
            "grade": case["grade"],
            "rubric": case["rubric"],
            "versions": {"mission": case.get("missionId"), "rubric": case.get("rubricVersion")},
        }
        try:
            response = judge(body)
        except Exception as exc:  # 한 건 실패로 전체를 멈추지 않고 callErrors로 셈
            print(f"  {case.get('caseId')}: 호출 실패 {type(exc).__name__}", file=sys.stderr)
            response = None
        rows.append({"case": case, "response": response})

    versions = Counter(
        (r["response"]["versions"].get("prompt"), r["response"]["versions"].get("model"))
        for r in rows
        if r["response"] is not None and r["response"]["versions"].get("prompt")
    )
    prompt, model = versions.most_common(1)[0][0] if versions else (None, None)
    by_scope: dict[str, list[dict]] = {}
    by_mission: dict[str, list[dict]] = {}
    for r in rows:
        by_scope.setdefault(scope_key(r["case"]), []).append(r)
        by_mission.setdefault(str(r["case"].get("missionId")), []).append(r)
    return {
        "prompt": prompt,
        "model": model,
        "overall": summarize(rows),
        "scopes": {k: summarize(v) for k, v in sorted(by_scope.items())},
        # 기준 미달 미션은 판정하지 않고 기록만 (기능명세 3.5)
        "missions": {k: summarize(v) for k, v in sorted(by_mission.items())},
        # 검증 통과 요소만 충족 표시 (NFR-AIQ-01) → judgeVerified 결정 근거
        "elements": element_agreement(rows),
    }


def element_agreement(rows: list[dict]) -> dict:
    """미션·요소별 일치율. key = '<missionId>/<elementId>'. 사람-AI는 HELD 제외."""
    acc: dict[str, dict[str, list]] = {}
    for r in rows:
        raters = r["case"]["raters"]
        ai = {}
        if r["response"] is not None and r["response"]["result"] != "HELD":
            ai = {e["elementId"]: e["satisfied"] for e in r["response"]["elements"]}
        for e in r["case"]["rubric"]["elements"]:
            eid = e["elementId"]
            slot = acc.setdefault(f"{r['case'].get('missionId')}/{eid}", {"hh": [], "ha": []})
            slot["hh"].append((raters["r1"][eid], raters["r2"][eid]))
            if eid in ai:
                slot["ha"] += [(raters[k][eid], ai[eid]) for k in RATERS]
    return {
        key: {
            "cases": len(v["hh"]),
            "judgedCases": len(v["ha"]) // len(RATERS),
            "humanHumanAgreement": _rate(v["hh"]),
            "humanAiAgreement": _rate(v["ha"]),
        }
        for key, v in sorted(acc.items())
    }


def compare(current: dict, baseline: dict) -> dict:
    """전체 지표의 차이 (현재 - 기준선). 한쪽이 None이면 None."""

    def diff(a: dict, b: dict) -> dict:
        out = {}
        for key, value in a.items():
            if isinstance(value, dict) and isinstance(b.get(key), dict):
                out[key] = diff(value, b[key])
            elif isinstance(value, (int, float)) and isinstance(b.get(key), (int, float)):
                out[key] = round(value - b[key], 3)
        return out

    return {
        "baseline": f"{baseline.get('prompt')} / {baseline.get('model')}",
        "overall": diff(current["overall"], baseline["overall"]),
    }


def registry_evaluation(summary: dict, args: argparse.Namespace, report_path: str) -> dict:
    """모델 레지스트리 등록 `evaluation` 필드 (api-spec 5.2). 문자열은 모두 비어 있지 않게."""
    o = summary["overall"]
    return {
        "datasetId": args.dataset_id,
        "datasetVersion": args.dataset_version,
        "baselineVersion": args.baseline_version or "없음(최초 기준선)",
        "comparisonReport": (
            f"{report_path} | 사람-사람 결과 QWK {o['humanHuman']['resultQwk']}, "
            f"사람-AI 결과 QWK {o['humanAi']['resultQwk']}, 보류 비율 {o['heldRatio']}"
        ),
        "trainingEvaluationSeparation": (
            "판정은 학습 없는 프롬프트 방식. 평가 답안은 프롬프트에 넣지 않은 고정 자료"
        ),
        "quoteAccuracy": f"인용 불일치 보류 비율 {o['quoteMismatchRatio']} (LLM 호출 사례 기준)",
        "calculationAccuracy": "해당 없음: 서술·논술 판정은 계산을 하지 않음",
        "humanReview": args.human_review,
        "evaluatedScopes": sorted(summary["scopes"]),
    }


def http_judge(base_url: str, token: str, timeout: float = 40) -> Judge:
    import httpx

    client = httpx.Client(base_url=base_url, headers={"X-Internal-Token": token}, timeout=timeout)

    def judge(body: dict) -> dict:
        response = client.post("/internal/judgments", json=body)
        response.raise_for_status()
        return response.json()

    return judge


def run(args: argparse.Namespace, judge: Judge) -> tuple[Path, Path]:
    cases = load_cases(args.cases)
    summary = evaluate(cases, judge)
    summary["dataset"] = {
        "id": args.dataset_id,
        "version": args.dataset_version,
        "cases": len(cases),
    }
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        summary["comparison"] = compare(summary, baseline)
        args.baseline_version = (
            args.baseline_version or f"{baseline.get('prompt')}/{baseline.get('model')}"
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{args.dataset_id}@{args.dataset_version}__{summary['prompt']}__{summary['model']}"
    name = name.replace("/", "_")
    report = args.out_dir / f"{name}.json"
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evaluation = args.out_dir / f"{name}.evaluation.json"
    rel = report.relative_to(ROOT) if report.is_relative_to(ROOT) else report
    evaluation.write_text(
        json.dumps(registry_evaluation(summary, args, str(rel)), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return report, evaluation


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--dataset-version", required=True)
    ap.add_argument(
        "--human-review",
        required=True,
        help="평가자 검토 기록 또는 그 참조 (레지스트리 humanReview)",
    )
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--token", default="")
    ap.add_argument("--baseline", type=Path, help="비교할 이전 결과 요약 JSON")
    ap.add_argument(
        "--baseline-version", help="비교 기준 버전 이름 (없으면 --baseline의 프롬프트/모델)"
    )
    ap.add_argument("--out-dir", type=Path, default=ROOT / "evaluation" / "results" / "judgment")
    return ap.parse_args(argv)


def main() -> None:
    args = parse_args()
    report, evaluation = run(args, http_judge(args.base_url, args.token))
    summary = json.loads(report.read_text(encoding="utf-8"))
    print(json.dumps(summary["overall"], ensure_ascii=False, indent=2))
    print(f"요약: {report}\n레지스트리 evaluation: {evaluation}")


if __name__ == "__main__":
    main()
