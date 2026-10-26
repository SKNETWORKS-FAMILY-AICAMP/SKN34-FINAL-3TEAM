"""CPU 추론 속도 측정 (scoring-service는 CPU로 추론함).

글 하나를 채점하는 데 걸리는 시간을 잰다 (토큰화 + 모델 계산).
속도는 모델 구조와 글 길이로 정해지므로 학습 전 모델로 재도 학습 후와 같다.
학생 글 대신 길이만 맞춘 예시 문장을 쓴다 (AI Hub 데이터 불필요).

실행:
    uv run python scripts/latency.py --model klue/roberta-base
    uv run python scripts/latency.py --model checkpoints/klue_roberta-base_descriptive_seed42
"""

import argparse
import platform
import statistics
import time

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

PROMPT = "[학년] 초5 [지시문] 글을 쓸 때 통일성이 무엇이며 왜 필요한지 설명하세요."
SENTENCE = (
    "친구와 이야기할 때 서로의 생각을 존중하면 오해가 줄어들고 의사소통이 잘 된다. "
)


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 CPU 추론 속도")
    parser.add_argument("--model", default="klue/roberta-base")
    parser.add_argument("--chars", type=int, nargs="+", default=[200, 650, 1200])
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--threads", type=int, default=0, help="0이면 기본값")
    args = parser.parse_args()

    if args.threads:
        torch.set_num_threads(args.threads)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=9, ignore_mismatched_sizes=True
    )
    model.eval()

    print(
        f"CPU: {platform.processor() or platform.machine()} / 스레드 {torch.get_num_threads()}"
    )
    print(f"모델: {args.model} / 반복 {args.runs}회\n")
    print("글자 수 | 토큰 수 | 중앙값(ms) | 95%(ms)")

    for n_chars in args.chars:
        text = (SENTENCE * (n_chars // len(SENTENCE) + 1))[:n_chars]
        times = []
        for i in range(args.runs + 3):  # 처음 3번은 준비 운동이라 버림
            start = time.perf_counter()
            enc = tokenizer(
                PROMPT,
                text,
                truncation="only_second",
                max_length=args.max_length,
                return_tensors="pt",
            )
            with torch.no_grad():
                # klue/roberta 토크나이저는 두 번째 문장에 token_type_id=1을 붙이지만
                # 모델은 0만 알아서 넣으면 에러. train.py와 같게 두 개만 넘긴다
                model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"])
            if i >= 3:
                times.append((time.perf_counter() - start) * 1000)
        times.sort()
        p95 = times[int(len(times) * 0.95) - 1]
        n_tokens = enc["input_ids"].shape[1]
        print(
            f"{n_chars:>6} | {n_tokens:>6} | {statistics.median(times):>10.0f} | {p95:>7.0f}"
        )


if __name__ == "__main__":
    main()
