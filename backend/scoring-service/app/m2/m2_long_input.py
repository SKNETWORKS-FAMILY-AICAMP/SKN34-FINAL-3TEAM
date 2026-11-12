"""M2 긴 글 토큰화 (11/12): 512토큰에 안 들어가면 앞 + 끝을 같이 읽음
(지금은 앞만 읽어 논술 마지막 칸이 잘릴 수 있음) - 들어가는 글: scoring-
service 지금 코드와 완전히 같은 결과(tokenizer(first, text,
truncation="only_second", ...)) - 안 들어가는 글: 글 토큰
중 앞 head개 + 끝 (남은 칸 − head)개. head = 남은 칸 ×
250/495 (11/12 시험: 남은 칸 495 → 앞 250 + 끝 245)
11/12 VL 긴 논술 글 155편, 전문가 3명 평균과 상관: 앞만 구성
0.373·내용 0.339·표현 0.387 → 앞+끝 0.386·0.356·0.397
(채점 1번, 시간 같음) - 돌려주는 값: (inputs, truncated).
inputs는
input_ids·attention_mask(+token_type_ids) 텐서
dict → LoadedModel.predict 그대로 쓰는 법
(service.infer의 tokenizer(...) 자리): inputs,
truncated = encode_head_tail(tokenizer, first,
text, max_length=length)
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
