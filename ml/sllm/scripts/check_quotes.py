"""'원문에 없는 인용'이 지어낸 건지, 맞춤법만 고쳐 옮긴 건지 숫자로 가른다.

eval_samples.jsonl(생성 결과)과 valid.jsonl(학생 글)을 id로 맞춰서,
전문가 정답 / 학습 전 / 학습 후 세 가지 각각의 인용을 이렇게 나눈다.
- 그대로: 띄어쓰기만 빼면 글에 그대로 있음
- 거의 같음: 글 안에 비슷도 0.8 이상인 구간이 있음 (맞춤법·조사만 바꿔 옮긴 것)
- 없음: 비슷한 구간도 없음 (지어냈을 가능성)

화면에는 숫자만 찍는다.

실행:
    python check_quotes.py
"""

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

QUOTE = re.compile(r"[\"“”'‘’]([^\"“”'‘’]{2,80})[\"“”'‘’]")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def best_ratio(q: str, essay: str) -> float:
    n = len(q)
    best = 0.0
    for size in (n - 2, n, n + 2):
        if size < 2:
            continue
        for i in range(0, max(1, len(essay) - size + 1)):
            m = SequenceMatcher(None, q, essay[i : i + size], autojunk=False)
            if m.real_quick_ratio() <= best or m.quick_ratio() <= best:
                continue
            best = max(best, m.ratio())
            if best >= 0.99:
                return best
    return best


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--samples", type=Path, default=Path("/workspace/outputs/eval_samples.jsonl"))
    p.add_argument("--data", type=Path, default=Path("/workspace/data/jsonl/valid.jsonl"))
    p.add_argument("--near", type=float, default=0.8)
    args = p.parse_args()

    essays = {}
    with args.data.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                prompt = rec["messages"][0]["content"]
                essays[rec["id"]] = norm(prompt.split("[글]\n", 1)[1].split("\n\n[항목 점수", 1)[0])

    names = (("reference", "전문가 정답"), ("base", "학습 전 Gemma"), ("lora", "학습 후 LoRA"))
    stats = {k: {"답": 0, "인용": 0, "그대로": 0, "거의 같음": 0, "없음": 0, "없음 있는 답": 0} for k, _ in names}
    with args.samples.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            s = json.loads(line)
            essay = essays.get(s["id"])
            if essay is None:
                continue
            for key, _ in names:
                if key not in s:
                    continue
                st = stats[key]
                st["답"] += 1
                missing = 0
                for q in QUOTE.findall(s[key]):
                    q = norm(q)
                    if not q:
                        continue
                    st["인용"] += 1
                    if q in essay:
                        st["그대로"] += 1
                    elif best_ratio(q, essay) >= args.near:
                        st["거의 같음"] += 1
                    else:
                        st["없음"] += 1
                        missing += 1
                st["없음 있는 답"] += missing > 0

    for key, label in names:
        st = stats[key]
        if not st["답"]:
            continue
        q = max(1, st["인용"])
        print(
            f"[{label}] 답 {st['답']}개, 인용 {st['인용']}개 → "
            f"그대로 {st['그대로']} ({st['그대로'] / q:.0%}), "
            f"거의 같음 {st['거의 같음']} ({st['거의 같음'] / q:.0%}), "
            f"없음 {st['없음']} ({st['없음'] / q:.0%}) / 없음이 하나라도 있는 답 {st['없음 있는 답']}개"
        )


if __name__ == "__main__":
    main()
