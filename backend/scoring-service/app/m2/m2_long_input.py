"""담당자 제공 11/12 c판 앞+끝 토큰화.

입력 한도 이하는 기존 only_second 토큰화와 같다.
한도 초과는 글 토큰의 앞 room*250/495개와 남은 수만큼 끝을 사용한다.
"""


def encode_head_tail(
    tokenizer, first: str, text: str, max_length: int = 512, return_tensors: str = "pt"
):
    first_ids = tokenizer(first, add_special_tokens=False)["input_ids"]
    text_ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    room = max_length - len(first_ids) - tokenizer.num_special_tokens_to_add(pair=True)
    if room <= 0:
        raise ValueError("first too long")
    if len(text_ids) <= room:
        return tokenizer(
            first,
            text,
            truncation="only_second",
            max_length=max_length,
            return_tensors=return_tensors,
        ), False
    head = round(room * 250 / 495)
    kept = text_ids[:head] + text_ids[len(text_ids) - (room - head) :]
    ids = (
        tokenizer.build_inputs_with_special_tokens(first_ids, kept)
        if hasattr(tokenizer, "build_inputs_with_special_tokens")
        else [
            tokenizer.cls_token_id,
            *first_ids,
            tokenizer.sep_token_id,
            *kept,
            tokenizer.sep_token_id,
        ]
    )
    import torch

    t = torch.tensor([ids])
    return {
        "input_ids": t,
        "token_type_ids": torch.zeros_like(t),
        "attention_mask": torch.ones_like(t),
    }, True
