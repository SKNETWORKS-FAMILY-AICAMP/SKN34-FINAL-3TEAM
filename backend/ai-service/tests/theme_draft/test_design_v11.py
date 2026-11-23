"""#782 설계 v11(운영 기준)·v12: 약속이 틀린 대화는 LLM이 다시 쓰고 마지막 시도에만 코드 문장.

- v12(사용자 결정 2026-11-23 "다시 써도 계속 틀리는 대화는 코드로"): 대화에 남은 사유가
  ASK_PROMISE뿐이면 사유를 넣어 다시 만들고, 마지막 시도(상한·마감)에도 약속뿐이면 코드 약속 문장
  (put_promise) → 통과하면 그 대화를 두고 PROMISE_FALLBACK 경고(v11은 첫 시도에서 곧바로)
- put_promise는 돕는 사람의 부탁 문장을 덮어쓰지 않음(줄 수 상한이면 곤란한 말 줄을 바꿈)
- 코드 약속 문장은 감각마다 짧은 꼴 셋을 같은 감각 부탁 날 순서로 돌려 씀(장소 이름 없음), 모든
  꼴이 40자 안·ASK_PROMISE 검사 통과
- 글 검토 뒤 단서를 고친 길: v12부터 약속이 틀린 요일을 돌려주고(promise_redo) 그 요일 대화만
  LLM이 다시 씀(코드 문장으로 바꿔 넣지 않음)
"""

from types import SimpleNamespace
from typing import Any

from app.config import get_settings
from app.theme_draft import checks, prompts
from app.theme_draft.checks import DAYS, LINE_MAX
from app.theme_draft.models import GeneratedLine
from app.theme_draft.nodes.dialogue import FALLBACK, promise_redo
from tests.theme_draft.fixtures import HELPER, dialogue
from tests.theme_draft.test_design_v10_a import ask_theme, story_day, with_promise
from tests.theme_draft.test_graph import gen_llm, review_llm, run
from tests.theme_draft.test_theme_structure import _draft

GRADE = 3


def no_promise(day: str, request: str, keep_fourth: bool = True) -> list[GeneratedLine]:
    """셋째 줄(돕는 사람의 약속)을 약속 없는 부탁으로 바꾼 대화 줄."""
    lines = [*dialogue(day).lines]
    lines[2] = GeneratedLine(speaker=HELPER[day], text=request)
    return lines if keep_fourth else [lines[1], lines[2], lines[3]]


# ---------------------------------------------------------------- 1. 마지막 시도에만 대신(그래프)
LAST_TRY = get_settings().theme_max_regen + 1  # 첫 생성 포함 대화 시도 수


def test_promise_only_problem_regenerates_then_code_at_last_attempt() -> None:
    """월요일 대화에 계속 약속이 없으면(남은 사유 ASK_PROMISE뿐) 사유를 넣어 다시 만들고 마지막
    시도에만 코드 문장(v12, v11은 첫 시도에서 곧바로)."""
    request = "안내문 정리 좀 같이 해 줄래?"
    lines = no_promise("MON", request, keep_fourth=False)  # 모델 3줄 + 코드 첫 줄 = 4줄
    gen = gen_llm(dlg=lambda n, d: dialogue(d, lines=lines) if d == "MON" else dialogue(d))
    response = run(gen, review_llm())
    assert response.failure is None
    counts = {d: gen.count("GeneratedDialogue", d) for d in DAYS}
    assert counts == {**dict.fromkeys(DAYS, 1), "MON": LAST_TRY}
    assert "ASK_PROMISE MON" in gen.users("GeneratedDialogue", "MON")[1]
    mon = next(x for x in response.dialogues if x.day == "MON")
    said = [(x.speaker, x.text) for x in mon.lines]
    # 줄 수 상한 아래라 마지막 뭉치 줄 앞에 넣음(부탁 줄은 그대로)
    assert said[-2] == (HELPER["MON"], "도와주면 그때 본 걸 알려 줄게.")
    assert (HELPER["MON"], request) in said and said[-1][0] == "뭉치"
    warned = [(w.stage, w.item, w.reason.split(" ")[0]) for w in response.warnings]
    assert warned == [("DIALOGUE", "MON", FALLBACK)]


def test_other_reason_still_regenerates() -> None:
    """약속과 다른 사유(화자)가 같이 걸리면 지금처럼 사유를 넣어 다시(대신하지 않음)."""
    bad = [*no_promise("MON", "안내문 정리 좀 같이 해 줄래?")]
    bad[1] = GeneratedLine(speaker="할머니", text="여기야.")

    def dlg(n: int, d: str | None) -> Any:
        return dialogue(d, lines=bad) if d == "MON" and n == 1 else dialogue(d)

    gen = gen_llm(dlg=dlg)
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedDialogue", "MON") == 2
    assert "ASK_PROMISE MON" in gen.users("GeneratedDialogue", "MON")[-1]
    assert not [w for w in response.warnings if w.stage == "DIALOGUE"]


def test_two_fallback_days_get_different_sentences() -> None:
    """월·목 둘 다 끝까지 약속이 없으면 둘 다 대신 — 같은 감각(본 것)이라도 다른 문장(요일 순서로만
    돌리면 월·목은 세 칸 떨어져 같은 문장)."""
    requests = {"MON": "안내문 정리 좀 같이 해 줄래?", "THU": "문구 정리 좀 같이 해 줄래?"}

    def dlg(n: int, d: str | None) -> Any:
        return dialogue(d, lines=no_promise(d, requests[d])) if d in requests else dialogue(d)

    gen = gen_llm(dlg=dlg)
    response = run(gen, review_llm())
    assert response.failure is None
    assert (
        gen.count("GeneratedDialogue", "MON") == gen.count("GeneratedDialogue", "THU") == LAST_TRY
    )
    put: dict[str, str] = {}
    for day, request in requests.items():
        out = next(x for x in response.dialogues if x.day == day)
        # 줄 수 상한(5줄)이라 부탁뿐인 줄 뒤에 붙임
        line = next(x.text for x in out.lines if x.text.startswith(request))
        put[day] = line[len(request) :].strip().rstrip(".")
        assert put[day] in prompts.PROMISE_FORMS["SEEN"]
    assert put["MON"] != put["THU"]
    warned = sorted((w.item, w.reason.split(" ")[0]) for w in response.warnings)
    assert warned == [("MON", FALLBACK), ("THU", FALLBACK)]


# ---------------------------------------------------------------- 2. 부탁 줄은 덮어쓰지 않음
HELPER_NAME = "공원 관리인"
SENTENCE = "도와주면 그때 본 걸 알려 줄게."
FIRST = {"speaker": "지호", "text": "보리를 찾으러 왔어."}
LAST = {"speaker": "뭉치", "text": "같이 도와 보자!"}
MUNG = {"speaker": "뭉치", "text": "여기구나!"}


def helper_line(text: str) -> dict[str, str]:
    return {"speaker": HELPER_NAME, "text": text}


def put(lines: list[dict[str, str]]) -> list[dict[str, str]] | None:
    out = checks.put_promise(lines, HELPER_NAME, SENTENCE, GRADE)
    assert out is None or all(len(x["text"]) <= LINE_MAX for x in out)
    return out


def test_put_promise_at_max_replaces_complaint_not_request() -> None:
    complaint, request = helper_line("안내문 글이 너무 막막해."), helper_line("같이 정리해 줄래?")
    out = put([FIRST, complaint, request, MUNG, LAST])  # 초3 상한 5줄
    assert out == [FIRST, helper_line(SENTENCE), request, MUNG, LAST]
    # 부탁이 첫 줄이고 곤란한 말이 뒤에 오면 곤란한 말 줄을 바꿈
    out = put([FIRST, request, complaint, MUNG, LAST])
    assert out == [FIRST, request, helper_line(SENTENCE), MUNG, LAST]


def test_put_promise_at_max_keeps_request_in_mixed_line() -> None:
    mixed = helper_line("글이 막막해. 같이 정리해 줄래?")
    out = put([FIRST, MUNG, mixed, MUNG, LAST])
    assert out is not None and out[2] == helper_line(f"같이 정리해 줄래? {SENTENCE}")
    # 부탁에 붙이면 40자를 넘으면 넣지 않음(None → 지금처럼 다시)
    long_ask = helper_line("공원 입구 안내문에 들어갈 글을 같이 정리해 줄래?")
    assert len(f"{long_ask['text']} {SENTENCE}") > LINE_MAX
    assert put([FIRST, MUNG, long_ask, MUNG, LAST]) is None


def test_put_promise_strips_long_promise_but_keeps_request() -> None:
    """부탁과 약속이 한 줄인데 바꾸면 40자가 넘으면 약속 문장만 빼고 따로 넣음(전에는 줄 전체를
    약속으로 바꿔 부탁이 사라졌음)."""
    ask = "공원 입구 안내문에 들어갈 글을 같이 정리해 줄래?"
    both = helper_line(f"{ask} 도와주면 고마운 걸 알려 줄게.")
    out = put([FIRST, both, LAST])
    assert out == [FIRST, helper_line(ask), helper_line(SENTENCE), LAST]


def test_put_promise_replaces_existing_promise_sentence_only() -> None:
    promise = helper_line("고마워. 도와주면 고마운 걸 알려 줄게.")
    out = put([FIRST, helper_line("같이 정리해 줄래?"), promise, MUNG, LAST])
    assert out is not None and out[2] == helper_line(f"고마워. {SENTENCE}")
    assert out[1] == helper_line("같이 정리해 줄래?")


# ---------------------------------------------------------------- 3. 코드 약속 문장
def test_fallback_forms_rotate_within_same_sense_days() -> None:
    theme = ask_theme()  # 부탁 날 월·수·목(본 것)·금(일지)
    got = {d: prompts.ask_promise(theme, checks.theme_day(theme, d)) for d in DAYS}
    assert [got[d] for d in ("MON", "WED", "THU")] == list(prompts.PROMISE_FORMS["SEEN"])
    assert got["FRI"] == "도와주면 내 일지를 보여 줄게"
    # 장소 이름은 넣지 않음(잃어버린 물건·시간 탐정은 장소가 후보 이름일 수 있음)
    for d in DAYS:
        assert str(checks.theme_day(theme, d)["place"]) not in got[d]
    # 넘겨받은 요일 칸(단서를 고친 길)으로도 같은 순서를 셈
    assert prompts.ask_promise(theme, story_day("그때 창문에 달빛이 비쳤어!")) == got["THU"]


def sense_day(theme: dict[str, Any], sense: str, medium: str | None = None) -> dict[str, Any]:
    """월요일을 그 감각의 부탁 날로."""
    d = checks.theme_day(theme, "MON")
    if sense == "RECORD":
        d["evidence"] = {"kind": "RECORD", "when": "그때"}
        theme["evidencePlan"] = {"MON": {"kind": "RECORD", "medium": medium}}
        return d
    d["evidence"] = {"kind": "SIGHTING", "when": "그때"}
    feature = {"SEEN": "물기", "HEARD": "들린 소리", "TASTED": "남은 맛", "SMELLED": "남은 냄새"}
    d["condition"] = {**d["condition"], "feature": feature[sense]}
    return d


def test_every_fallback_form_passes_promise_checks() -> None:
    cases = [(s, None) for s in ("SEEN", "HEARD", "TASTED", "SMELLED")]
    cases += [("RECORD", m) for m in checks.RECORD_MEDIA]
    for sense, medium in cases:
        theme = ask_theme()
        d = sense_day(theme, sense, medium)
        assert checks.promise_sense(theme, d) == (sense, medium)
        texts = set()
        for turn in range(3):
            forms = prompts.PROMISE_FORMS[sense]
            if sense == "RECORD":
                assert medium is not None
                josa = "을" if (ord(medium[-1]) - 0xAC00) % 28 else "를"
                verb = "들려줄게" if medium == "녹음" else "보여 줄게"
                text = forms[turn].format(medium=medium, josa=josa, verb=verb) + "."
            else:
                text = forms[turn] + "."
            texts.add(text)
            lines = [{"speaker": d["helper"], "text": text}]
            assert len(text) <= LINE_MAX, text
            assert not checks.ask_promise_missing(d, lines), text
            assert checks.ask_promise_mismatch(theme, d, lines) is None, text
        assert len(texts) == 3, (sense, medium)
        # ask_promise가 실제로 내는 문장도 그 꼴 중 하나
        assert prompts.ask_promise(theme, d) + "." in texts


# ---------------------------------------------------------------- 4. 단서를 고친 길
def recheck_ctx() -> Any:
    return SimpleNamespace(
        prompt=SimpleNamespace(body=prompts), settings=get_settings(), grade=GRADE
    )


def heard_thu(theme: dict[str, Any]) -> dict[str, Any]:
    fixed = checks.theme_day(theme, "THU")
    fixed.update(
        clue="창고 쪽에서 쿵 소리가 들렸어.",
        condition={"kind": "STORY", "feature": "", "allowed": []},
        evidence={"kind": "SIGHTING", "when": "그때"},
    )
    return theme


def test_promise_redo_returns_day_to_regenerate() -> None:
    """단서를 고쳐 약속 감각이 바뀐 날(본 것 → 들은 소리)의 약속이 틀리면 그 요일을 사유와 함께
    돌려줌(v12: 코드 문장으로 바꿔 넣지 않고 그 요일 대화만 LLM이 다시)."""
    old = ask_theme()
    new = heard_thu(ask_theme())
    lines = [FIRST, *with_promise("THU", "같이 해 주면 그때 본 것도 알려 줄게.")]
    state = {
        "theme": old,
        "dialogues": {"THU": lines},
        "drafts": {"THU": _draft(checks.DAY_TYPE["THU"])},
    }
    out = promise_redo(recheck_ctx(), state, new)  # type: ignore[arg-type]
    assert list(out) == ["THU"]
    assert [r.split(" ")[0] for r in out["THU"]] == ["ASK_PROMISE"]
    # 감각이 그대로인 날은 보지 않음
    assert promise_redo(recheck_ctx(), state, ask_theme()) == {}  # type: ignore[arg-type]
