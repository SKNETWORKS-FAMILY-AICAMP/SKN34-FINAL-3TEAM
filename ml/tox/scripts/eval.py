"""답변 표현 분류(#690) 평가: 임계값을 정하고 시험셋 지표를 낸다.

1. 꼭 통과할 글(learning.md 16장 기준안 "오탐 0")
   - 데모 미션 시드 문장: `backend/learning-service/db/seed/demo_missions.sql`의 한글 문자열
   - 학생 글 함정: 단어 목록 시험 `ExpressionPolicyTest.kt`에서 "막지 않음"으로 고정한 문장
2. 임계값: 검증셋에서 ① 꼭 통과할 글의 가장 높은 확률보다 크고 ② 정상 글 오탐률이 1% 이하인 값
   (0.01 간격) 가운데 F1이 가장 큰 값. 같으면 큰 값
3. 그 임계값으로 시험셋(K-MHaS test)·APEACH(`apeach.jsonl`이 있으면) 지표
판정은 api-spec 4.3.4와 같다: 글을 `max_length`·`stride` 토큰 창으로 나눠 한 창이라도
막을 확률이 임계값 이상이면 걸림.
결과 JSON에는 숫자와 꼭 통과할 글(우리가 쓴 문장) 중 높은 확률 몇 개만 남긴다.
학습·검증·시험 글 원문은 넣지 않고, 외부 API로 보내지 않는다.

    uv run python scripts/eval.py --model checkpoints/kcelectra-base-s42 --out results/eval_tox.json
    #  고른 임계값을 train_info.json에 쓰려면 --write, int8(동적 양자화) 정확도는 --int8
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re

from quant import QUANTIZATION, WINDOW_BATCH, quantize_int8
from train import binary_metrics, check_artifact, read_jsonl

REPO = pathlib.Path(__file__).resolve().parents[3]
DEMO_SQL = "backend/learning-service/db/seed/demo_missions.sql"
WEB_DEMO = "frontend/web/src/data/classroom/demoGateway.ts"
TRAP_TEST = (
    "backend/learning-service/src/test/kotlin/com/sagomungchi/learning/answer/domain/"
    "ExpressionPolicyTest.kt"
)
MAX_FPR = 0.01
GRID = [round(i / 100, 2) for i in range(1, 100)]


def sql_sentences(text: str) -> list[str]:
    """ExpressionPolicyTest의 데모 시드 시험과 같은 방식: 작은따옴표 문자열 중 한글이 있는 것."""
    out = []
    for line in text.splitlines():
        for m in re.finditer(r"'((?:[^']|'')*)'", line):
            s = m.group(1).replace("''", "'")
            if re.search(r"[가-힣]", s):
                out.append(s)
    return out


def ts_sentences(text: str) -> list[str]:
    """웹 데모 데이터(TS)의 따옴표·백틱 문자열 중 한글이 있는 것. `${...}` 자리는 지움."""
    out = []
    for m in re.finditer(r"([\"'`])((?:\\.|(?!\1).)*?)\1", text):
        s = re.sub(r"\$\{[^}]*\}", "", m.group(2)).replace("\\n", "\n")
        if re.search(r"[가-힣]", s):
            out.append(s)
    return out


def _string_list(text: str, start: int) -> list[str]:
    """start(`listOf(` 바로 뒤)부터 닫는 괄호까지의 큰따옴표 문자열."""
    out, i = [], start
    while i < len(text) and text[i] != ")":
        if text[i] == '"':
            m = re.compile(r'"((?:[^"\\]|\\.)*)"').match(text, i)
            out.append(m.group(1).replace('\\"', '"'))
            i = m.end()
        else:
            i += 1
    return out


def kotlin_pass_sentences(text: str) -> list[str]:
    """`assertAll(null, listOf(...))`와 미션 없이 부른 `assertEquals(null, check("..."))`의 문장."""
    out = []
    for m in re.finditer(r"assertAll\(\s*null\s*,\s*listOf\(", text):
        out += _string_list(text, m.end())
    out += re.findall(r'assertEquals\(\s*null\s*,\s*check\("((?:[^"\\]|\\.)*)"\)\)', text)
    return out


def kotlin_context_sentences(text: str) -> list[str]:
    """미션 본문을 같이 넘겨야 허용되는 문장(`check("...", 미션)`). 모델은 미션을 안 보므로
    임계값 조건에서 빼고 확률만 기록한다(#205 측정도 미션 없이는 막히는 예외로 둠)."""
    return re.findall(r'assertEquals\(\s*null\s*,\s*check\("((?:[^"\\]|\\.)*)"\s*,', text)


def must_pass(repo: pathlib.Path = REPO) -> dict[str, list[str]]:
    """꼭 통과할 글. #205의 "데모 문장 491"은 learning 데모 시드 + 웹 데모 데이터(11/02 기준,
    추출 스크립트 저장소 밖)라 지금 파일에서 같은 방식으로 다시 뽑는다."""
    demo = sql_sentences((repo / DEMO_SQL).read_text(encoding="utf-8"))
    web = ts_sentences((repo / WEB_DEMO).read_text(encoding="utf-8"))
    trap = kotlin_pass_sentences((repo / TRAP_TEST).read_text(encoding="utf-8"))
    return {
        "demo": list(dict.fromkeys(demo)),
        "web": list(dict.fromkeys(web)),
        "trap": list(dict.fromkeys(trap)),
    }


def pick_threshold(
    probs: list[float], labels: list[int], must_pass_max: float, max_fpr: float = MAX_FPR
) -> tuple[float | None, dict]:
    """조건을 만족하는 임계값 중 F1 최대. 없으면 (None, 이유)."""
    best = None
    for t in GRID:
        if t <= must_pass_max:
            continue
        m = binary_metrics(probs, labels, t)
        if m["falsePositiveRate"] > max_fpr:
            continue
        if best is None or m["f1"] >= best["f1"]:
            best = m
    if best is None:
        return None, {
            "reason": f"꼭 통과할 글 최고 확률 {must_pass_max:.4f}·오탐 {max_fpr} 조건 불가"
        }
    return best["threshold"], best


def score_texts(model, tokenizer, texts, max_length, stride, device, batch_size=64, per_text=False):
    """글마다 창별 막을 확률의 최댓값(api-spec 4.3.4).

    per_text: scoring과 같게 글 하나씩, 창 8개씩. int8은 묶음에 따라 확률이 달라져 이 길로 잰다.
    fp32는 묶음과 상관없이 같다(11/17 꼭 통과할 글 390개 차이 최대 3e-6).
    """
    import torch

    model.eval()
    out = []
    with torch.no_grad():
        if per_text:
            for text in texts:
                enc = tokenizer(
                    text,
                    truncation=True,
                    max_length=max_length,
                    stride=stride,
                    return_overflowing_tokens=True,
                    padding=True,
                    return_tensors="pt",
                )
                best = 0.0
                for i in range(0, len(enc["input_ids"]), WINDOW_BATCH):
                    part = {
                        k: enc[k][i : i + WINDOW_BATCH].to(device)
                        for k in ("input_ids", "attention_mask")
                    }
                    p = torch.softmax(model(**part).logits.float(), dim=-1)[:, 1]
                    best = max(best, p.max().item())
                out.append(best)
            return out
        for i in range(0, len(texts), batch_size):
            enc = tokenizer(
                texts[i : i + batch_size],
                truncation=True,
                max_length=max_length,
                stride=stride,
                return_overflowing_tokens=True,
                padding=True,
                return_tensors="pt",
            )
            owner = enc.pop("overflow_to_sample_mapping").tolist()
            enc = {k: v.to(device) for k, v in enc.items() if k in ("input_ids", "attention_mask")}
            p = torch.softmax(model(**enc).logits.float(), dim=-1)[:, 1].tolist()
            part = [0.0] * len(texts[i : i + batch_size])
            for j, prob in zip(owner, p, strict=True):
                part[j] = max(part[j], prob)
            out += part
    return out


def evaluate(args: argparse.Namespace, saved: dict | None = None) -> dict:
    """saved를 주면 글별 확률·라벨을 셋 이름으로 담는다(--save-probs, wordlist.py 입력)."""
    saved = {} if saved is None else saved
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    problems = check_artifact(args.model)
    if problems:
        raise SystemExit(f"모델 폴더 확인 필요: {problems}")
    info = json.loads((args.model / "train_info.json").read_text(encoding="utf-8"))
    device = "cuda" if torch.cuda.is_available() and not args.int8 else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model).to(device)
    if args.int8:  # scoring 로더와 같은 채널별 동적 양자화(CPU 전용, quant.py)
        model = quantize_int8(model)

    def score(texts):
        return score_texts(
            model, tokenizer, texts, info["max_length"], info["stride"], device, per_text=args.int8
        )

    sets = must_pass(args.repo)
    mp = {name: score(texts) for name, texts in sets.items()}
    context = kotlin_context_sentences((args.repo / TRAP_TEST).read_text(encoding="utf-8"))
    cprobs = score(context)
    mp_max = max(max(v) for v in mp.values() if v)
    valid = read_jsonl(args.data / "valid.jsonl", args.limit)
    valid_probs = score([x["text"] for x in valid])
    valid_labels = [x["label"] for x in valid]
    saved["valid"] = (valid_probs, valid_labels)
    threshold, chosen = pick_threshold(valid_probs, valid_labels, mp_max, args.max_fpr)

    def metrics_at(path: pathlib.Path):
        if not path.is_file():
            return None
        rows = read_jsonl(path, args.limit)
        probs = score([x["text"] for x in rows])
        labels = [x["label"] for x in rows]
        saved[path.stem] = (probs, labels)
        at = {"default0.5": binary_metrics(probs, labels, 0.5)}
        if threshold is not None:
            at["chosen"] = binary_metrics(probs, labels, threshold)
        return at

    top = sorted(
        ((p, name, t) for name in sets for p, t in zip(mp[name], sets[name], strict=True)),
        reverse=True,
    )[:10]
    return {
        "model": {"baseModel": info.get("baseModel"), "baseRevision": info.get("baseRevision")},
        "evaluatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "window": {"max_length": info["max_length"], "stride": info["stride"]},
        "int8": args.int8,
        "quantization": QUANTIZATION if args.int8 else "none",
        "scoring": "글 하나씩·창 8개씩(scoring과 같음)" if args.int8 else "64개씩 묶음",
        "rule": f"꼭 통과할 글 최고 확률 초과 · 검증 정상 오탐 ≤ {args.max_fpr} · F1 최대",
        "threshold": threshold,
        "valid": {"chosen": chosen, "default0.5": binary_metrics(valid_probs, valid_labels, 0.5)},
        "mustPass": {
            "counts": {name: len(texts) for name, texts in sets.items()},
            "maxProb": round(mp_max, 4),
            "flaggedAtChosen": 0 if threshold is not None else None,
            "flaggedAt0.5": sum(1 for v in mp.values() for p in v if p >= 0.5),
            "top10": [{"set": n, "text": t, "prob": round(p, 4)} for p, n, t in top],
            "contextOnly": [
                {"text": t, "prob": round(p, 4)} for t, p in zip(context, cprobs, strict=True)
            ],
        },
        "test": metrics_at(args.data / "test.jsonl"),
        "apeach": metrics_at(args.data / "apeach.jsonl"),
        "limit": args.limit,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True, type=pathlib.Path)
    ap.add_argument("--data", default=pathlib.Path("data/processed"), type=pathlib.Path)
    ap.add_argument("--repo", default=REPO, type=pathlib.Path)
    ap.add_argument("--out", default=None, type=pathlib.Path)
    ap.add_argument("--max-fpr", default=MAX_FPR, type=float)
    ap.add_argument("--limit", default=None, type=int, help="동작 확인용: 각 셋 N개만")
    ap.add_argument("--write", action="store_true", help="고른 임계값을 train_info.json에 씀")
    ap.add_argument("--int8", action="store_true", help="동적 양자화한 모델로 잼(CPU)")
    ap.add_argument("--save-probs", type=pathlib.Path, help="글별 확률·라벨 npz(글 없음)")
    args = ap.parse_args(argv)
    args.out = args.out or pathlib.Path(f"results/eval_tox{'_int8' if args.int8 else ''}.json")
    saved: dict = {}
    result = evaluate(args, saved)
    if args.save_probs:
        import numpy as np

        args.save_probs.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            args.save_probs,
            **{f"{k}_probs": np.array(p, dtype=np.float32) for k, (p, _) in saved.items()},
            **{f"{k}_labels": np.array(y, dtype=np.int8) for k, (_, y) in saved.items()},
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"임계값 {result['threshold']} · 꼭 통과할 글 최고 확률 {result['mustPass']['maxProb']}")
    print(f"결과 → {args.out}")
    if result["threshold"] is None:
        raise SystemExit("조건을 만족하는 임계값 없음: top10을 보고 원인 확인")
    if args.write and not args.limit:
        path = args.model / "train_info.json"
        info = json.loads(path.read_text(encoding="utf-8"))
        info["threshold"] = result["threshold"]
        mode = "int8" if args.int8 else "fp32"
        info["thresholdSource"] = f"eval.py {result['evaluatedAt'][:10]} {mode}: {result['rule']}"
        info["quantization"] = QUANTIZATION if args.int8 else "none"  # api-spec 5.2 로더 기준
        path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"train_info.json threshold → {result['threshold']}")


if __name__ == "__main__":
    main()
