"""학습 전(원래 Gemma) vs 학습 후(LoRA) 해설 비교.

검증 데이터(valid.jsonl) 앞에서 N개를 골라 두 모델로 생성하고, 숫자로만 집계한다.
- 형식: 질문에 준 항목이 빠짐없이, 같은 순서로 '- 항목: 설명' 줄로 나왔는지
- 점수 노출: "3점" 같은 표현, 숫자가 섞였는지
- 인용: 따옴표 안 문구가 학생 글에 실제로 있는지
- 전문가 문장과 겹침: 글자 2-gram F1 (참고용)
- 길이·생성 시간

화면에는 숫자만 찍는다. 글·문장 원문은 사람 검토용 파일(--samples-out)에만 저장한다.
생각 끈 상태(학습과 같은 생성 프롬프트)로 생성한다.

실행:
    python eval_lora.py --n 50
"""

import argparse
import json
import re
import statistics
import time
from pathlib import Path

import torch
from unsloth import FastModel

SCORE_PAT = re.compile(r"[0-9０-９]\s*점")
DIGIT = re.compile(r"[0-9０-９]")
QUOTE = re.compile(r"[\"“”'‘’]([^\"“”'‘’]{2,80})[\"“”'‘’]")
LINE = re.compile(r"^\s*-\s*([^:：]+?)\s*[:：]\s*(.+)$")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def parse_prompt(prompt: str) -> tuple[str, list[str]]:
    essay = prompt.split("[글]\n", 1)[1].split("\n\n[항목 점수", 1)[0]
    scores = prompt.split("[항목 점수 (1~5)]\n", 1)[1]
    labels = [m.group(1) for m in (LINE.match(x) for x in scores.splitlines()) if m]
    return essay, labels


def parse_output(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2).strip()) for m in (LINE.match(x) for x in text.splitlines()) if m]


def bigram_f1(a: str, b: str) -> float:
    def grams(s):
        s = norm(s)
        return [s[i : i + 2] for i in range(len(s) - 1)]

    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    pool, hit = list(gb), 0
    for g in ga:
        if g in pool:
            pool.remove(g)
            hit += 1
    p, r = hit / len(ga), hit / len(gb)
    return 0.0 if hit == 0 else 2 * p * r / (p + r)


def score(prompt: str, output: str, reference: str) -> dict:
    essay, labels = parse_prompt(prompt)
    got = parse_output(output)
    ref = dict(parse_output(reference))
    got_labels = [lab for lab, _ in got]
    quotes = QUOTE.findall(output)
    essay_n = norm(essay)
    texts = [t for _, t in got]
    # 항목 이름("내용 1")의 숫자는 빼고 설명 문장만 검사. 형식이 깨져 줄을 못 읽었으면 전체를 검사
    body = "\n".join(texts) if texts else output
    return {
        "형식 완전": got_labels == labels,
        "항목 누락률": sum(lab not in got_labels for lab in labels) / max(1, len(labels)),
        "점수 표현": bool(SCORE_PAT.search(body)),
        "숫자 포함": bool(DIGIT.search(body)),
        "인용 수": len(quotes),
        "원문에 없는 인용": sum(norm(q) not in essay_n for q in quotes),
        "항목당 글자": statistics.mean(len(t) for t in texts) if texts else 0.0,
        "전문가 문장 겹침": statistics.mean(bigram_f1(t, ref.get(lab, "")) for lab, t in got) if got else 0.0,
    }


def summarize(name: str, rows: list[dict], secs: list[float]) -> None:
    n = len(rows)
    print(f"\n[{name}] {n}개")
    print(f"  형식 완전            {sum(r['형식 완전'] for r in rows)}/{n}")
    print(f"  항목 누락률 평균     {statistics.mean(r['항목 누락률'] for r in rows):.1%}")
    print(f"  점수 표현(N점) 있음  {sum(r['점수 표현'] for r in rows)}/{n}")
    print(f"  숫자 포함            {sum(r['숫자 포함'] for r in rows)}/{n}")
    q = sum(r["인용 수"] for r in rows)
    bad = sum(r["원문에 없는 인용"] for r in rows)
    print(f"  인용                 {q}개 중 원문에 없음 {bad}개")
    print(f"  항목당 글자 중앙값   {statistics.median(r['항목당 글자'] for r in rows):.0f}")
    print(f"  전문가 문장 겹침     {statistics.mean(r['전문가 문장 겹침'] for r in rows):.3f} (글자 2-gram F1)")
    print(f"  생성 시간 중앙값     {statistics.median(secs):.1f}초")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--adapter", default="/workspace/outputs/explain-lora/adapter")
    p.add_argument("--data", type=Path, default=Path("/workspace/data/jsonl/valid.jsonl"))
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--max-new", type=int, default=800)
    p.add_argument("--samples-out", type=Path, default=Path("/workspace/outputs/eval_samples.jsonl"))
    p.add_argument("--skip-base", action="store_true", help="원래 모델 생성은 건너뜀")
    args = p.parse_args()

    model, processor = FastModel.from_pretrained(
        model_name=args.adapter, max_seq_length=4096, load_in_4bit=False
    )
    tok = getattr(processor, "tokenizer", processor)
    FastModel.for_inference(model)

    with args.data.open(encoding="utf-8") as f:
        recs = [json.loads(x) for x in f if x.strip()][: args.n]

    def generate(prompt: str) -> tuple[str, float]:
        text = tok.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
        )
        ids = tok(text, add_special_tokens=False, return_tensors="pt").to(model.device)
        t0 = time.time()
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=args.max_new, do_sample=False)
        new = out[0][ids["input_ids"].shape[1] :]
        return tok.decode(new, skip_special_tokens=True).strip(), time.time() - t0

    results = {"base": ([], []), "lora": ([], [])}
    args.samples_out.parent.mkdir(parents=True, exist_ok=True)
    with args.samples_out.open("w", encoding="utf-8") as f:
        for i, rec in enumerate(recs, 1):
            prompt, reference = rec["messages"][0]["content"], rec["messages"][1]["content"]
            sample = {"id": rec["id"], "reference": reference}
            for name in ("lora", "base"):
                if name == "base" and args.skip_base:
                    continue
                if name == "base":
                    with model.disable_adapter():
                        text, secs = generate(prompt)
                else:
                    text, secs = generate(prompt)
                sample[name] = text
                results[name][0].append(score(prompt, text, reference))
                results[name][1].append(secs)
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            print(f"{i}/{len(recs)} 완료", flush=True)

    for name, label in (("base", "학습 전 Gemma"), ("lora", "학습 후 LoRA")):
        if results[name][0]:
            summarize(label, *results[name])
    print(f"\n사람 검토용 원문: {args.samples_out} (Pod 안에서만 보기)")


if __name__ == "__main__":
    main()
