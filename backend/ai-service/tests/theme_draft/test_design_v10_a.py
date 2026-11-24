"""#782 설계 v10 A(약속 줄·같은 주 안의 같은 말): 흐름 글은 LLM이 쓰고 코드는 뜻만 준다.

- promise_sense: 기록 날은 그 매체, 특징 이름의 감각(소리·맛·냄새), 사건 단서 날은 단서 마지막 말이
  듣기일 때만 들은 날(v9 '그 소리가 난 뒤 창문에 달빛이 비쳤어'가 들은 날이던 회귀)
- 대화 요청·지시문은 약속 뜻만(예시 문장 없음), ASK_PROMISE는 약속 유무 + 감각이 맞는지
- 남은 사유가 ASK_PROMISE뿐이면 약속 줄을 코드 문장으로 바꿔 넣고 경고(설계 v12부터 마지막
  시도에만, v11은 첫 시도에서 곧바로)
- 같은 주 같은 말 다시 만들기(dedupe_dialogues)는 설계 v11에서 뺌
- fix_clues: 고친 단서로 약속 감각이 바뀐 날은 약속을 다시 보고 틀리면 그 요일 대화만 다시(설계 v12)
"""

import copy
from typing import Any

from app.config import get_settings
from app.theme_draft import checks, prompts
from app.theme_draft.checks import DAYS
from app.theme_draft.graph import build_graph
from app.theme_draft.models import GeneratedLine
from app.theme_draft.nodes.dialogue import FALLBACK
from tests.theme_draft.fixtures import (
    HELPER,
    dialogue,
    story_review,
    valid_theme,
)
from tests.theme_draft.test_graph import fixes, gen_llm, review_llm, run
from tests.theme_draft.test_theme_structure import _draft

GRADE = 3
# 기본 요청(request_body)의 미션 방식 배정(test_graph.WAYS와 같음)
WAYS = {
    "MON": checks.ASK,
    "TUE": checks.INVESTIGATE,
    "WED": checks.ASK,
    "THU": checks.ASK,
    "FRI": checks.ASK,
}


def ask_theme() -> dict[str, Any]:
    theme = valid_theme()
    for d in theme["days"]:
        d["missionWay"] = WAYS[d["day"]]
    return theme


def story_day(clue: str) -> dict[str, Any]:
    """사건 단서 날(특징 없음, 목격)."""
    d = copy.deepcopy(checks.theme_day(ask_theme(), "THU"))
    d.update(
        clue=clue,
        condition={"kind": "STORY", "feature": "", "allowed": []},
        evidence={"kind": "SIGHTING", "when": "그때"},
    )
    return d


def with_promise(day: str, text: str) -> list[dict[str, str]]:
    lines = [x.model_dump() for x in dialogue(day).lines]
    lines[2]["text"] = text
    return lines


# ---------------------------------------------------------------- 1. promise_sense
def test_promise_sense_record_and_feature() -> None:
    theme = ask_theme()
    fri = checks.theme_day(theme, "FRI")
    # 배정이 없는 예전 저장본은 증거 발견 줄의 기록 낱말
    assert checks.promise_sense(theme, fri) == ("RECORD", "일지")
    theme["evidencePlan"] = {"FRI": {"kind": "RECORD", "medium": "사진"}}
    assert checks.promise_sense(theme, "FRI") == ("RECORD", "사진")
    mon = copy.deepcopy(checks.theme_day(theme, "MON"))
    for feature, sense in (
        ("들린 소리", "HEARD"),
        ("남은 맛", "TASTED"),
        ("남은 냄새", "SMELLED"),
        ("꽃 향", "SMELLED"),
        ("물기", "SEEN"),
        ("간 방향", "SEEN"),  # '방향'은 냄새가 아님
    ):
        mon["condition"] = {**mon["condition"], "feature": feature}
        assert checks.promise_sense(theme, mon) == (sense, None), feature


def test_story_day_hears_only_when_last_clause_is_hearing() -> None:
    """v9 회귀: 단서 어디든 '소리'면 들은 날이라 달빛(본 것)에도 '들은 소리'를 약속함."""
    theme = ask_theme()
    for clue, sense in (
        ("그 소리가 난 뒤 창문에 달빛이 비쳤어!", "SEEN"),
        ("그 소리가 난 뒤에 창문에 달빛이 비쳤어.", "SEEN"),
        ("쿵 소리가 났고, 창문에 불이 켜졌어.", "SEEN"),
        ("그때 등불이 파란색으로 깜빡였어!", "SEEN"),
        ("그 소리는 한 번만 짧게 났어!", "HEARD"),
        ("창고 쪽에서 쿵 소리가 들렸어요.", "HEARD"),
        ("불이 꺼지자, 노랫소리가 들렸던 것 같아.", "HEARD"),
    ):
        assert checks.promise_sense(theme, story_day(clue)) == (sense, None), clue
    # #782 설계 v11: 코드 대신 문장은 감각마다 꼴 셋을 돌려 씀
    moon = story_day("그 소리가 난 뒤 창문에 달빛이 비쳤어!")
    assert prompts.ask_promise(theme, moon) in prompts.PROMISE_FORMS["SEEN"]
    heard = story_day("창고 쪽에서 쿵 소리가 들렸어.")
    assert prompts.ask_promise(theme, heard) in prompts.PROMISE_FORMS["HEARD"]


# ---------------------------------------------------------------- 2. 대화 요청·지시문은 뜻만
def test_dialogue_request_gives_meaning_not_sentence() -> None:
    theme = ask_theme()
    user = prompts.dialogue_user(theme, "MON", _draft("ANALYZE"), GRADE, [])
    # #782 설계 v12: 오늘 일은 조건에만(약속 내용을 오늘과 엮지 않음)
    assert (
        "돕는 사람의 약속(③): 오늘 부탁한 일을 도와주면(조건은 오늘 일로 자기 말로) 그때 "
        "본 것을 알려 주겠다는 뜻으로 한 줄. 약속 말에 '그때'와 알려 줄 것을 꼭 넣고" in user
    )
    # 약속 검사(ASK_PROMISE)가 알아보는 꼴과 같은 말
    # (10차: '그때'를 빼게 해 맞는 약속을 '없음'으로 잡음)
    assert (
        "'오늘·아까·○○에서'를 붙이지 않음" in user and "도와주면 그때 본 걸 알려 줄게" not in user
    )
    assert "도와주면 그때 본 걸 알려 줄게" not in user
    record = prompts.dialogue_user(theme, "FRI", _draft("REFLECT"), GRADE, [])
    assert "그때 자기 일지를 알려 주겠다는 뜻" in record
    heard = copy.deepcopy(theme)
    checks.theme_day(heard, "MON")["condition"]["feature"] = "들린 소리"
    assert "들은 소리를 알려 주겠다는 뜻" in prompts.dialogue_user(
        heard, "MON", _draft("ANALYZE"), GRADE, []
    )
    system = prompts.DIALOGUE_SYSTEM
    assert "한 줄 40자 안, '막막해'만 쓰지 않음" in system  # #782 설계 v11: 짧게
    assert "그때 본 것(기록 날은 가진 기록)을 알려 주겠다고 함" not in system
    assert "ASK_PROMISE" in system


# ---------------------------------------------------------------- 3. ASK_PROMISE 감각
def test_ask_promise_catches_sense_mismatch() -> None:
    theme = ask_theme()
    mon, fri = checks.theme_day(theme, "MON"), checks.theme_day(theme, "FRI")

    def mismatch(day: dict, text: str) -> str | None:
        return checks.ask_promise_mismatch(theme, day, with_promise(day["day"], text))

    # 본 날(물기 특징)
    assert mismatch(mon, "도와주면 그때 내가 들은 소리를 알려 줄게.")
    assert not mismatch(mon, "도와주면 그때 본 걸 알려 줄게.")
    assert not mismatch(mon, "도와주면 내 녹음을 들려줄게.")  # 기록은 감각으로 보지 않음
    # 들은 날
    heard = {**mon, "condition": {**mon["condition"], "feature": "들린 소리"}}
    assert mismatch(heard, "도와주면 그때 본 걸 알려 줄게.")
    assert mismatch(heard, "도와주면 내가 봤던 걸 알려 줄게.")
    assert not mismatch(heard, "도와주면 내가 들어 봤던 걸 알려 줄게.")  # '들어 봤'은 듣기
    assert not mismatch(heard, "도와주면 그때 내가 들은 소리를 알려 줄게.")
    # 기록 날은 그 매체
    assert mismatch(fri, "도와주면 그때 본 걸 알려 줄게.")
    assert not mismatch(fri, "도와주면 내 일지를 보여 줄게.")
    # 대화 검사 사유는 ASK_PROMISE 하나(그 요일 다시)이고 예시 문장 없이 뜻을 말함
    bad = checks.check_dialogue(
        theme,
        "FRI",
        {"lines": with_promise("FRI", "도와주면 그때 본 걸 알려 줄게.")},
        _draft("REFLECT"),
        GRADE,
        get_settings().followup_example_overlap_chars,
    )
    assert [r.split(" ")[0] for r in bad] == ["ASK_PROMISE"]
    assert "자기 일지를 알려 주겠다는 뜻" in bad[0] and "예:" not in bad[0]
    # 수사 날은 보지 않음
    tue = checks.theme_day(theme, "TUE")
    assert not checks.ask_promise_mismatch(theme, tue, with_promise("TUE", "들은 걸 알려 줄게."))


# ---------------------------------------------------------------- 4. 코드 문장 대신 넣기
def test_put_promise_replaces_or_inserts_within_line_limit() -> None:
    helper, sentence = "공원 관리인", "도와주면 그때 본 걸 알려 줄게."
    first = {"speaker": "지호", "text": "보리를 찾으러 왔어."}
    last = {"speaker": "뭉치", "text": "같이 도와 보자!"}
    ask = {"speaker": helper, "text": "안내문 정리 좀 도와줄래?"}
    # 약속 같은 줄은 그 문장만 바꿈(부탁은 그대로)
    mixed = {"speaker": helper, "text": "같이 정리해 줄래? 도와주면 고마운 걸 알려 줄게."}
    out = checks.put_promise([first, mixed, last], helper, sentence, GRADE)
    assert out is not None and out[1]["text"] == "같이 정리해 줄래? " + sentence
    # 약속 줄이 없으면 마지막 뭉치 줄 앞에 넣음
    out = checks.put_promise([first, ask, last], helper, sentence, GRADE)
    assert out == [first, ask, {"speaker": helper, "text": sentence}, last]
    # 줄 수 상한(초3 5줄)이면 #782 설계 v11: 부탁 줄은 덮어쓰지 않음 — 돕는 사람 줄이 모두
    # 부탁뿐이면 첫 줄 부탁 뒤에 붙임(40자 안)
    full = [first, {"speaker": "뭉치", "text": "여기구나!"}, ask, ask, last]
    out = checks.put_promise(full, helper, sentence, GRADE)
    assert out is not None and len(out) == 5
    assert out[2] == {"speaker": helper, "text": f"{ask['text']} {sentence}"}
    assert out[0] == first and out[3] == ask and out[-1] == last
    assert checks.put_promise([first, last], helper, "가" * 41, GRADE) is None  # 40자 넘음


def test_graph_fallback_inserts_promise_when_only_ask_promise_remains() -> None:
    """월요일 모델이 끝까지 약속을 안 쓰면(남은 사유 ASK_PROMISE뿐) 대화를 빼지 않고 코드 문장
    (#782 설계 v12: 사유를 넣어 다시 만들고 마지막 시도에만)."""
    no_promise = [
        *dialogue("MON").lines[:2],
        GeneratedLine(speaker=HELPER["MON"], text="안내문 정리 좀 같이 해 줄래?"),
        dialogue("MON").lines[3],
    ]
    gen = gen_llm(dlg=lambda n, d: dialogue(d, lines=no_promise) if d == "MON" else dialogue(d))
    response = run(gen, review_llm())
    assert response.failure is None
    assert gen.count("GeneratedDialogue", "MON") == get_settings().theme_max_regen + 1
    mon = next(x for x in response.dialogues if x.day == "MON")
    assert mon.lines[-1].speaker == "뭉치"
    # 줄 수 상한(5줄)이라 돕는 사람의 부탁뿐인 줄 뒤에 붙임(부탁은 그대로)
    assert (HELPER["MON"], "안내문 정리 좀 같이 해 줄래? 도와주면 그때 본 걸 알려 줄게.") in [
        (x.speaker, x.text) for x in mon.lines
    ]
    warned = [w for w in response.warnings if w.stage == "DIALOGUE"]
    assert [(w.item, w.reason.split(" ")[0]) for w in warned] == [("MON", FALLBACK)]


def test_graph_other_reason_with_ask_promise_still_omits_day() -> None:
    """ASK_PROMISE와 다른 사유(화자)가 함께 남으면 지금처럼 그 요일 대화를 빼고 경고."""
    bad = [GeneratedLine(speaker="할머니", text="여기야.")] * 4
    gen = gen_llm(dlg=lambda n, d: dialogue(d, lines=bad) if d == "MON" else dialogue(d))
    response = run(gen, review_llm())
    assert [d.day for d in response.dialogues] == ["TUE", "WED", "THU", "FRI"]
    reasons = [w.reason for w in response.warnings if (w.stage, w.item) == ("DIALOGUE", "MON")]
    assert reasons and not any(r.startswith(FALLBACK) for r in reasons)


# ---------------------------------------------------------------- 5. 같은 주 안의 같은 말
def test_graph_dialogue_goes_straight_to_review() -> None:
    """#782 설계 v11: 같은 주 같은 말을 다시 만들던 dedupe_dialogues는 뺌(v9처럼)."""
    edges = {(e.source, e.target) for e in build_graph().get_graph().edges}
    assert ("generate_dialogue", "review_story") in edges
    assert "dedupe_dialogues" not in set(build_graph().get_graph().nodes)


# ---------------------------------------------------------------- 6. 단서를 고친 길
THU_HEARD = "내가 골목 안쪽에서 보리가 짖는 소리를 들었어."


def test_graph_fixed_clue_changing_sense_regenerates_that_dialogue() -> None:
    """글 검토 CLUE_LOGIC으로 목요일 단서가 본 것 → 들은 소리로 바뀌면 목요일 약속('본 것')이
    틀림 — #782 설계 v12: 목요일 대화만 사유를 넣어 다시 만들고(모델이 계속 '본 것'이면) 마지막
    시도에만 코드 문장(들은 소리). v11은 다시 만들지 않고 곧바로 코드 문장."""
    review = review_llm(
        story=lambda n, d: (
            story_review({"CLUE_LOGIC": "FAIL"}, {"CLUE_LOGIC": ["THU"]})
            if n == 1
            else story_review()
        )
    )
    gen = gen_llm(fix=lambda n, d: fixes(("THU.clue", THU_HEARD)))
    response = run(gen, review)
    assert response.failure is None
    last_try = get_settings().theme_max_regen + 1
    counts = {d: gen.count("GeneratedDialogue", d) for d in DAYS}
    assert counts == {**dict.fromkeys(DAYS, 1), "THU": 1 + last_try}
    assert "ASK_PROMISE THU" in gen.users("GeneratedDialogue", "THU")[1]
    assert gen.count("GeneratedTheme") == 1  # 줄거리는 다시 만들지 않음
    thu = next(x for x in response.dialogues if x.day == "THU")
    texts = [x.text for x in thu.lines]
    assert "도와주면 그때 내가 들은 소리를 알려 줄게." in texts
    assert "같이 해 주면 그때 본 것도 알려 줄게." not in texts
    warned = [(w.stage, w.item, w.reason.split(" ")[0]) for w in response.warnings]
    assert warned == [("DIALOGUE", "THU", FALLBACK)]


def test_tell_verb_is_not_heard_promise() -> None:
    """8차 a: '본 걸 들려줄게'(이야기해 줄게)를 들은 것으로 봐 대화를 29번 다시 만듦."""
    theme = ask_theme()
    d = checks.theme_day(theme, "MON")
    d["condition"] = {"kind": "STORY", "feature": "", "allowed": []}
    d["clue"] = "그때 창문에 달빛이 비쳤어!"
    helper = d["helper"]
    for text in ("도와주면 그때 본 걸 들려줄게.", "도와주면 내가 본 걸 이야기로 들려줄게."):
        lines = [{"speaker": helper, "text": text}]
        assert checks.ask_promise_mismatch(theme, d, lines) is None, text
    lines = [{"speaker": helper, "text": "도와주면 그때 내가 들은 소리를 알려 줄게."}]
    assert checks.ask_promise_mismatch(theme, d, lines)
