# ruff: noqa: E501
# 담당자 제공 합성 문장 원문을 보존한다.
"""긴 글 토큰화 시험 (가짜 토크나이저, 학생 글 없음, torch 필요). 실행: python -m pytest test_m2_long_input.py"""

import pytest

torch = pytest.importorskip("torch")
from app.m2.m2_long_input import encode_head_tail  # noqa: E402


class FakeTok:
    cls_token_id, sep_token_id = 0, 2

    def __call__(
        self,
        a,
        b=None,
        add_special_tokens=True,
        truncation=None,
        max_length=None,
        return_tensors=None,
    ):
        def ids(s):
            return [10 + int(w) for w in s.split()]

        if b is None and not add_special_tokens:
            return {"input_ids": ids(a)}
        x = ids(b)[: max_length - len(ids(a)) - 3]
        out = [0, *ids(a), 2, *x, 2]
        t = torch.tensor([out])
        return {
            "input_ids": t,
            "token_type_ids": torch.zeros_like(t),
            "attention_mask": torch.ones_like(t),
        }

    def num_special_tokens_to_add(self, pair=True):
        return 3


def test_short_same_as_now():
    tok = FakeTok()
    inp, cut = encode_head_tail(tok, "1 2", " ".join(map(str, range(5))), max_length=20)
    assert (
        not cut
        and inp["input_ids"].tolist()
        == tok("1 2", "0 1 2 3 4", max_length=20)["input_ids"].tolist()
    )


def test_long_keeps_head_and_tail():
    tok = FakeTok()
    text = " ".join(map(str, range(100)))
    inp, cut = encode_head_tail(tok, "1", text, max_length=20)
    ids = inp["input_ids"][0].tolist()
    assert cut and len(ids) == 20 and ids[-2] == 10 + 99 and ids[3] == 10 + 0
