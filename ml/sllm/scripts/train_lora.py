"""Gemma 4 26B-A4B 16비트 LoRA 학습 (설명 sLLM).

- 모델은 16비트 그대로 올린다(load_in_4bit=False). A100 80GB 기준.
- LoRA는 어텐션(q·k·v·o)에만 붙인다. MoE 전문가(MLP)에 붙이면 vLLM 서빙 쪽 LoRA
  지원이 불확실해서 기본은 끔(--mlp로 켤 수 있음).
- 답(assistant) 부분만 손실을 계산한다. 질문(글·점수) 토큰은 -100으로 가림.

실행 (먼저 짧게 시험):
    python train_lora.py --max-steps 20
본 학습:
    python train_lora.py
"""

import argparse
import inspect
import json
import math
from pathlib import Path

import torch
from unsloth import FastModel  # unsloth는 transformers보다 먼저 import

from transformers import Trainer, TrainingArguments


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def turn_end(tok) -> str:
    # 답 뒤에 템플릿이 붙이는 꼬리(턴 종료 토큰 등)를 알아낸다
    probe = "@@ANSWER@@"
    full = tok.apply_chat_template(
        [{"role": "user", "content": "q"}, {"role": "assistant", "content": probe}],
        tokenize=False,
    )
    return full.split(probe, 1)[1]


def encode(tok, rec: dict, max_len: int, end: str):
    # 추론 때와 같은 모양: (생성 프롬프트까지의 질문) + 답 + 턴 종료.
    # Gemma 4 템플릿은 생성 프롬프트에만 붙는 부분이 있어 '전체 대화' 렌더링과 앞부분이
    # 다르므로, 전체를 따로 렌더링하지 않고 직접 이어 붙인다.
    user, answer = rec["messages"][0], rec["messages"][1]
    prompt = tok.apply_chat_template([user], tokenize=False, add_generation_prompt=True)
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    a_ids = tok(answer["content"] + end, add_special_tokens=False)["input_ids"]
    f_ids = p_ids + a_ids
    if len(f_ids) > max_len:
        return None
    labels = [-100] * len(p_ids) + f_ids[len(p_ids) :]
    return {"input_ids": f_ids, "labels": labels}


class Collator:
    def __init__(self, pad_id: int):
        self.pad_id = pad_id

    def __call__(self, batch):
        n = max(len(b["input_ids"]) for b in batch)
        ids, labels, mask = [], [], []
        for b in batch:
            pad = n - len(b["input_ids"])
            ids.append(b["input_ids"] + [self.pad_id] * pad)
            labels.append(b["labels"] + [-100] * pad)
            mask.append([1] * len(b["input_ids"]) + [0] * pad)
        return {
            "input_ids": torch.tensor(ids),
            "labels": torch.tensor(labels),
            "attention_mask": torch.tensor(mask),
        }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="/workspace/models/gemma-4-26b-qat")
    p.add_argument("--data-dir", type=Path, default=Path("/workspace/data/jsonl"))
    p.add_argument("--out", type=Path, default=Path("/workspace/outputs/explain-lora"))
    p.add_argument("--max-len", type=int, default=3072)
    p.add_argument("--rank", type=int, default=16)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--epochs", type=float, default=1.0)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--max-steps", type=int, default=-1, help="시험용. -1이면 epochs대로")
    p.add_argument("--mlp", action="store_true", help="MLP(전문가)에도 LoRA")
    args = p.parse_args()

    model, processor = FastModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_len,
        load_in_4bit=False,
        full_finetuning=False,
    )
    tok = getattr(processor, "tokenizer", processor)
    # 기본: 언어 모델 어텐션(q·k·v·o)만. finetune_mlp_modules=False만으로는 Unsloth가
    # MoE 전문가(experts.gate_up_proj·down_proj)에도 LoRA를 붙여서 정규식으로 직접 지정한다.
    attn_only = (
        r"(?:.*?(?:language|text).*?self_attn\.(?:q_proj|k_proj|v_proj|o_proj))"
        r"|(?:model\.layers\.\d+\.self_attn\.(?:q_proj|k_proj|v_proj|o_proj))"
    )
    model = FastModel.get_peft_model(
        model,
        target_modules=None if args.mlp else attn_only,
        finetune_vision_layers=False,
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=args.mlp,
        r=args.rank,
        lora_alpha=args.rank,
        lora_dropout=0,
        bias="none",
        random_state=42,
    )

    trainable = [n for n, prm in model.named_parameters() if prm.requires_grad]
    experts = [n for n in trainable if "expert" in n]
    print(f"학습 파라미터 텐서 {len(trainable)}개, 그중 전문가(experts) {len(experts)}개")
    print("예시:", trainable[:4])
    if experts and not args.mlp:
        raise SystemExit("전문가에 LoRA가 붙었음. --mlp 없이 돌렸으니 중단 (target_modules 확인 필요)")
    if not trainable:
        raise SystemExit("학습할 LoRA 파라미터가 없음 (target_modules 정규식이 안 맞음)")

    end = turn_end(tok)
    print(f"턴 종료 꼬리: {end!r}")
    demo_prompt = tok.apply_chat_template(
        [{"role": "user", "content": "(질문)"}], tokenize=False, add_generation_prompt=True
    )
    print(f"생성 프롬프트 모양: {demo_prompt!r}")

    data = {}
    for split in ("train", "valid"):
        recs = load_jsonl(args.data_dir / f"{split}.jsonl")
        enc = [e for e in (encode(tok, r, args.max_len, end) for r in recs) if e]
        lens = sorted(len(e["input_ids"]) for e in enc)
        print(
            f"{split}: {len(enc):,}/{len(recs):,}개 사용 (max-len 초과 {len(recs) - len(enc):,}), "
            f"토큰 중앙값 {lens[len(lens) // 2] if lens else 0}"
        )
        data[split] = enc

    steps_per_epoch = math.ceil(len(data["train"]) / (args.batch * args.grad_accum))
    print(f"한 에폭 {steps_per_epoch} 스텝")
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id

    total_steps = args.max_steps if args.max_steps > 0 else math.ceil(steps_per_epoch * args.epochs)
    # 시험 실행(--max-steps)이면 마지막 스텝에 평가·저장을 한 번씩 해서 그 부분까지 점검
    every = args.max_steps if args.max_steps > 0 else max(20, steps_per_epoch // 5)
    print(f"총 {total_steps} 스텝, 평가·저장 {every} 스텝마다")
    wanted = dict(
        output_dir=str(args.out / "checkpoints"),
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        # transformers 5에는 warmup_ratio가 없어 스텝 수로 준다 (전체의 3%)
        warmup_steps=max(1, int(total_steps * 0.03)),
        bf16=True,
        logging_steps=5,
        eval_strategy="steps",
        eval_steps=every,
        save_strategy="steps",
        save_steps=every,
        save_total_limit=3,
        report_to="none",
        remove_unused_columns=False,
        optim="adamw_8bit",
        seed=42,
    )
    # 버전마다 인자 이름이 달라서, 이 버전에 없는 인자는 빼고 이름을 알려 준다
    accepted = set(inspect.signature(TrainingArguments.__init__).parameters)
    dropped = sorted(k for k in wanted if k not in accepted)
    if dropped:
        print(f"이 transformers 버전에 없는 인자라 뺌: {dropped}")
    trainer = Trainer(
        model=model,
        train_dataset=data["train"],
        eval_dataset=data["valid"],
        data_collator=Collator(pad_id),
        args=TrainingArguments(**{k: v for k, v in wanted.items() if k in accepted}),
    )
    trainer.train()
    model.save_pretrained(str(args.out / "adapter"))
    tok.save_pretrained(str(args.out / "adapter"))
    print(f"어댑터 저장: {args.out / 'adapter'}")


if __name__ == "__main__":
    main()
