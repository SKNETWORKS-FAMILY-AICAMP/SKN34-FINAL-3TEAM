# ruff: noqa: E501
# 담당자 제공 합성 문장 원문을 보존한다.
"""합성 예시로만 시험 (학생 글 없음). 실행: python -m pytest test_m2_text_guard.py"""

from app.m2.m2_text_guard import prepare_essay

P = "여러분이 생각하는 SNS의 문제점과 해결 방안을 써 보세요."
BODY = (
    "나는 SNS를 쓰면 친구와 쉽게 소통할 수 있다고 생각한다. 하지만 잘못된 정보가 빠르게 퍼지는 문제가 있다. "
    "그래서 글을 올리기 전에 사실인지 확인하는 습관이 필요하다. 학교에서도 SNS를 바르게 쓰는 법을 가르쳐야 한다. "
    "또 하루에 SNS를 쓰는 시간을 정해 두면 공부와 휴식의 균형을 지킬 수 있다. 이렇게 하면 SNS의 좋은 점은 살리고 나쁜 점은 줄일 수 있다."
)


def test_normal_unchanged():
    g = prepare_essay(BODY, P)
    assert g.text == BODY and g.copied == 0 and not g.repeated and not g.too_short


def test_copied_prompt_removed():
    g = prepare_essay("SNS의 문제점과 해결 방안을 써 보세요. " + BODY, P)
    assert g.copied == 1 and g.text.startswith("나는 SNS를") and not g.too_short


def test_repeat_removed():
    first3 = ". ".join(BODY.split(". ")[:3]) + "."
    g = prepare_essay(BODY + " " + first3 + " " + first3, P)
    assert g.repeated and len(g.text) <= len(BODY) + 5


def test_only_copied_too_short():
    g = prepare_essay(P + " " + P, P)
    assert g.too_short and g.chars < 100


def test_empty_prompt_ok():
    g = prepare_essay(BODY, "")
    assert g.text == BODY and g.copied == 0


# ---- 11/12 c판 추가 ----
from app.m2.m2_text_guard import prepare_narrative, strip_labels  # noqa: E402

LABELED = "주장: 나는 SNS가 필요하다고 생각한다.\n까닭 1: 친구와 쉽게 소통할 수 있다.\n까닭 2: 정보를 빨리 얻는다.\n반대 의견에 답하기: 잘못된 정보는 확인하면 된다."


def test_labels_removed_keep_lines():
    t, n = strip_labels(LABELED)
    assert (
        n == 4
        and "주장:" not in t
        and "까닭 1" not in t
        and t.count("\n") == 3
        and t.startswith("나는 SNS가")
    )


def test_label_word_inside_sentence_kept():
    t, n = strip_labels("내 주장: 이것은 문장 안이다.\n까닭은 다음과 같다: 하나")
    assert n == 0 and t.startswith("내 주장:")


def test_custom_labels():
    t, n = strip_labels("생각: 가\n이유: 나", labels=("생각", "이유"))
    assert n == 2 and t == "가\n나"


def test_essay_strips_labels():
    g = prepare_essay(LABELED + " " + BODY, P)
    assert g.labels_removed == 4 and "반대 의견에 답하기" not in g.text


def test_narrative_short_still_scored():
    g = prepare_narrative(
        "물은 끓으면 수증기가 된다. 그래서 냄비 뚜껑에 물방울이 맺힌다.",
        "물이 끓을 때 생기는 일을 쓰시오.",
    )
    assert not g.too_short and g.short and g.chars < 100


def test_narrative_copy_and_repeat():
    q = "물이 끓을 때 냄비 뚜껑에 물방울이 맺히는 까닭을 쓰시오."
    body = "물이 끓으면 수증기가 생긴다. 수증기가 차가운 뚜껑에 닿는다. 그러면 다시 물방울로 바뀐다. 이것을 응결이라고 한다. 그래서 뚜껑 안쪽에 물방울이 맺힌다."
    g = prepare_narrative(q + " " + body, q)
    assert g.copied == 1 and g.text == body
    body.split(" ")
    rep = body + " " + "물이 끓으면 수증기가 생긴다. 수증기가 차가운 뚜껑에 닿는다. " * 2
    g2 = prepare_narrative(rep, q)
    assert g2.repeated and g2.text.count("수증기가 생긴다") == 1


def test_narrative_normal_unchanged():
    g = prepare_narrative(BODY, P)
    assert g.text == BODY and not g.short and not g.too_short and g.copied == 0
