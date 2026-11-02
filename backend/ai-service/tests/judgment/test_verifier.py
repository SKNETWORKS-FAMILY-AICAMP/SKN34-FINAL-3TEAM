import unicodedata

import pytest

from app.judgment.verifier import is_verbatim, visible_length

ANSWER = "나는 찬성해. 왜냐하면  쉬는 시간이 길면\n더 잘 놀 수 있기 때문이야."


@pytest.mark.parametrize(
    "quote",
    [
        "나는 찬성해",
        "쉬는 시간이 길면 더 잘 놀 수 있기 때문이야",  # 공백 2칸·줄바꿈 차이는 허용
        "  나는 찬성해.  ",
    ],
)
def test_verbatim_quotes_are_verified(quote: str) -> None:
    assert is_verbatim(quote, ANSWER)


@pytest.mark.parametrize(
    "quote",
    [
        "나는 찬성한다",  # 고쳐 씀
        "시간이 절약되니까",  # 지어냄
        "나는 찬성해 쉬는 시간이",  # 여러 곳 이어 붙임
        "",
        "   ",
        None,
    ],
)
def test_other_quotes_are_not_verified(quote: str | None) -> None:
    assert not is_verbatim(quote, ANSWER)


def test_unicode_normalization_is_allowed() -> None:
    decomposed = unicodedata.normalize("NFD", "찬성해")
    assert is_verbatim(decomposed, ANSWER)


def test_visible_length_ignores_whitespace() -> None:
    assert visible_length(" 몰 라 요 \n") == 3
