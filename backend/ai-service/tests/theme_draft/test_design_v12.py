"""#782 설계 v12(사용자 결정 2026-11-23 "기준 빼고 v12 구현해").

- 약속 말(조건 '~하면' 뒤)에 '오늘·아까'·전해 들은 말이 붙으면 ASK_PROMISE(조건의 '오늘'은 됨)
- 글 검토가 약속 줄만 틀렸다고 하면(promiseDays) 단서·줄거리가 아니라 그 요일 대화만 다시
- 단서를 고쳐 약속 감각이 바뀐 날도 그 요일 대화만 다시(after_fix_clues → generate_dialogue)
- 9차 치명 결함 종류 검사(그 칸 고쳐 쓰기): KEPT_CARRY·GIFT_CARRY·STORY_FEATURE·RECORD_HEARSAY·
  SOUND_TELLER·DAY_STEP_MADE(기록 언급), 미션 MISSION_TESTIMONY
"""

import copy
from typing import Any

from langgraph.types import Send

from app.mission_draft.models import Draft, MissionDraftRequest
from app.theme_draft import checks, graph
from app.theme_draft.nodes.review import promise_only_days
from app.theme_draft.regen import outside_targets
from tests.theme_draft.fixtures import DAY_TYPES, mission_draft, story_review
from tests.theme_draft.helpers import request_body
from tests.theme_draft.test_design_v10_a import ask_theme, with_promise
from tests.theme_draft.test_graph import gen_llm, review_llm, run
from tests.theme_draft.test_theme_structure import _draft


def codes(bad: list[str]) -> list[str]:
    return [r.split(" ")[0] for r in bad]


# ---------------------------------------------------------------- 1. 약속 말
def mismatch(text: str) -> str | None:
    theme = ask_theme()
    d = checks.theme_day(theme, "MON")  # 부탁 날, 본 것
    return checks.ask_promise_mismatch(theme, d, with_promise("MON", text))


def test_promise_with_now_or_hearsay_is_caught() -> None:
    # 9차 '도와주면 오늘 본 것도 알려 줄게'(42줄)·snd4b '가족에게 전해 들은 소리'
    assert "지금 일" in str(mismatch("도와주면 오늘 본 것도 알려 줄게."))
    assert "지금 일" in str(mismatch("글을 같이 정리해 주면, 내가 아까 본 걸 알려 줄게."))
    assert "전해 들은" in str(mismatch("도와주면 가족에게 전해 들은 소리를 알려 줄게."))


def test_today_in_condition_is_fine() -> None:
    """조건(오늘 부탁한 일)의 '오늘'은 지시문이 시키는 꼴이라 됨."""
    assert mismatch("오늘 글을 같이 써 주면, 그때 본 걸 알려 줄게.") is None
    assert mismatch("도와주면 그때 본 걸 알려 줄게.") is None


# ---------------------------------------------------------------- 2. 약속 줄만 틀림 → 대화만
def clue_fail(days: list[str], promise: list[str]) -> list[dict[str, Any]]:
    item = story_review({"CLUE_LOGIC": "FAIL"}, {"CLUE_LOGIC": days}, promise).items[0]
    return [item.model_dump()]


def test_promise_only_days() -> None:
    assert promise_only_days(clue_fail(["MON", "WED"], ["WED", "MON"])) == ["MON", "WED"]
    assert promise_only_days(clue_fail(["MON", "WED"], ["MON"])) == []  # 수요일은 단서 탓
    assert promise_only_days(clue_fail([], ["MON"])) == []  # 요일 없는 판정은 지금처럼
    other = story_review({"CLUE_LOGIC": "FAIL", "SAFETY": "FAIL"}, {"CLUE_LOGIC": ["MON"]}, ["MON"])
    fails = [x.model_dump() for x in other.items if x.verdict == "FAIL"]
    assert promise_only_days(fails) == []  # 다른 FAIL이 같이 있으면 지금처럼


def test_review_promise_fail_regenerates_only_that_dialogue() -> None:
    """첫 검토가 월요일 약속 줄만 틀렸다고 하면 월요일 대화만 다시(검토 사유를 넣어) 만들고 다시
    검토 — 줄거리·미션·단서 고쳐 쓰기 없음."""

    def story(n: int, d: str | None) -> Any:
        if n == 1:
            return story_review({"CLUE_LOGIC": "FAIL"}, {"CLUE_LOGIC": ["MON"]}, ["MON"])
        return story_review()

    gen = gen_llm()
    review = review_llm(story=story)
    response = run(gen, review)
    assert response.failure is None
    assert gen.count("GeneratedTheme") == 1
    assert gen.count("GeneratedDialogue", "MON") == 2
    assert all(gen.count("GeneratedDialogue", d) == 1 for d in ("TUE", "WED", "THU", "FRI"))
    assert "CLUE_LOGIC" in gen.users("GeneratedDialogue", "MON")[-1]
    assert review.count("GeneratedStoryReview") == 2


def test_after_fix_clues_sends_talk_days() -> None:
    theme = ask_theme()
    drafts = {d: _draft(checks.DAY_TYPE[d]) for d in checks.DAYS}
    state: dict[str, Any] = {
        "review_route": "REVIEW",
        "talk_seed": {"THU": ["ASK_PROMISE THU 약속"]},
        "theme": theme,
        "drafts": drafts,
    }
    sends = graph.after_fix_clues(state)  # type: ignore[arg-type]
    assert isinstance(sends, list) and len(sends) == 1 and isinstance(sends[0], Send)
    assert sends[0].node == "generate_dialogue"
    assert sends[0].arg["day"] == "THU" and sends[0].arg["seed"] == ["ASK_PROMISE THU 약속"]
    assert graph.after_fix_clues({**state, "talk_seed": {}}) == "review_story"  # type: ignore[arg-type]
    assert graph.after_fix_clues({**state, "review_route": "PLAN"}) == "plan_theme"  # type: ignore[arg-type]


def test_partial_regen_talk_inside_mission_targets_only() -> None:
    state: dict[str, Any] = {"partial": True, "redo_targets": ["MISSION:MON"]}
    assert not outside_targets(state, "TALK", ["MON"])  # type: ignore[arg-type]
    assert outside_targets(state, "TALK", ["WED"])  # type: ignore[arg-type]


# ---------------------------------------------------------------- 3. 9차 치명 결함 종류
def theme_of(code: str, **top: Any) -> dict[str, Any]:
    theme = copy.deepcopy(ask_theme())
    theme.update(storyType=code, **top)
    return theme


def test_kept_carry_origin_object() -> None:
    """9차 hand5b: 시작 이야기는 관리 선생님이 주워 맡김, 단서는 '내가 털장갑을 나르며'."""
    theme = theme_of("ORIGIN", branch="물건")
    theme["days"][1]["clue"] = "맡기기 전에 내가 털장갑을 나르며 맡아 보니 꽃 향은 아니었어!"
    assert "KEPT_CARRY" in codes(checks.kept_trace_problems(theme))
    theme["days"][1]["clue"] = "맡겨지기 전에 그 장갑이 벤치에 놓여 있을 때 보니 꽃 향은 아니었어!"
    assert "KEPT_CARRY" not in codes(checks.kept_trace_problems(theme))


def test_gift_carry_only_when_delivered() -> None:
    """9차 hand4: 시작 이야기 '배달돼'인데 '이모는 리본 상자를 안고 복도를 지나왔어'."""
    theme = theme_of(
        "GIFT",
        intro="오후 3시, 아린 앞으로 리본 상자가 배달돼 관리실 선반에 놓여 있다.",
        characters=[{"name": "아린", "look": "아이"}, {"name": "이모", "look": "어른"}],
    )
    theme["days"][0]["clue"] = "이모는 리본 상자를 안고 복도를 지나왔어!"
    assert "GIFT_CARRY" in codes(checks.v12_problems(theme))
    # 8차 hand3b처럼 배달원에게 건네는 것은 배달과 맞음
    theme["days"][0]["clue"] = "그때 이모가 리본 상자를 배달원에게 건네는 걸 내가 봤어!"
    assert "GIFT_CARRY" not in codes(checks.v12_problems(theme))


def test_story_clue_other_day_feature() -> None:
    """9차 auto5b: 수요일 사건 단서 '출입문 쪽으로', 금요일 특징 '출입문과 거리'."""
    theme = theme_of("LOST", intro="온유는 기차역에서 지갑을 잃어버렸다.")
    theme["features"] = [
        {"name": "출입문과 거리", "values": []},
        {"name": "바닥 무늬", "values": []},
    ]
    wed = theme["days"][2]
    wed["condition"] = {"kind": "STORY", "feature": "", "allowed": []}
    wed["clue"] = "내가 보니 지갑 끈이 스친 가는 자국이 출입문 쪽으로 이어졌어!"
    assert "STORY_FEATURE" in codes(checks.v12_problems(theme))
    # 흔적 낱말('자국'·'바닥')은 사건 단서에 흔해 보지 않음
    wed["clue"] = "내가 보니 지갑 끈이 스친 자국이 바닥을 따라 이어졌어!"
    assert "STORY_FEATURE" not in codes(checks.v12_problems(theme))


def test_record_hearsay_and_sound_teller() -> None:
    theme = theme_of("SOUND", intro="새봄은 할머니에게서 밤에 소리가 났다는 이야기를 전해 듣는다.")
    theme["days"][3]["clue"] = "내 일지엔 화단 지름이 2m도 5m도 아니래!"  # 9차 way6b
    theme["days"][1]["dayStep"] = "이웃에게 시골 학교에서 밤 소리 이야기를 들어, 와 봤어."  # snd5
    got = codes(checks.v12_problems(theme))
    assert "RECORD_HEARSAY" in got and "SOUND_TELLER" in got
    theme["days"][3]["clue"] = "내 일지엔 화단 지름이 2m도 5m도 아니라고 적혀 있어!"
    theme["days"][1]["dayStep"] = "밤 소리가 궁금해 자료실도 살펴보러 왔어."
    assert not {"RECORD_HEARSAY", "SOUND_TELLER"} & set(codes(checks.v12_problems(theme)))


def test_day_step_record_reference_must_exist() -> None:
    """9차 new4: 금요일 '일지에 나온 포장방 문턱', 목요일 일지는 '뒷문이 닫혀'."""
    theme = theme_of("PRANK")
    theme["days"][3]["clue"] = "내 일지에는 떡 접시가 비기 전까지 뒷문이 닫혀 있었다고 적혀 있어!"
    theme["days"][4]["dayStep"] = "일지에 나온 포장방 문턱도 살펴보러 왔어."
    assert "DAY_STEP_MADE" in codes(checks.v12_problems(theme))
    theme["days"][4]["dayStep"] = "일지에 나온 뒷문 쪽도 살펴보러 왔어."
    assert "DAY_STEP_MADE" not in codes(checks.v12_problems(theme))


def test_v12_reasons_are_single_field_fixes() -> None:
    reasons = [
        "KEPT_CARRY TUE clue 사유",
        "GIFT_CARRY MON clue 사유",
        "STORY_FEATURE WED clue 사유",
        "RECORD_HEARSAY THU clue 사유",
        "SOUND_TELLER TUE dayStep에 '이웃에게' 사유",
        "DAY_STEP_MADE FRI dayStep에 앞 요일 기록에 없는 것",
    ]
    assert set(checks.fix_targets(reasons)) == {
        "TUE.clue",
        "MON.clue",
        "WED.clue",
        "THU.clue",
        "TUE.dayStep",
        "FRI.dayStep",
    }


# ---------------------------------------------------------------- 4. 수사 날 문제의 증언
def investigate_codes(question_extra: str) -> list[str]:
    theme = checks.fill_rules_out(ask_theme())
    tue = checks.theme_day(theme, "TUE")  # 수사 날
    req = MissionDraftRequest.model_validate(
        {**request_body()["missions"][list(DAY_TYPES).index("TUE")], "gradeMin": 3, "gradeMax": 3}
    )
    question = f"{question_extra} {tue['missionMaterial']} 이 글이 믿을 만한지 까닭을 써 줘."
    draft = Draft.model_validate(mission_draft(DAY_TYPES["TUE"], question=question).model_dump())
    return codes(checks.material_problems(theme, req, draft))


def test_investigate_question_must_not_promise_missing_testimony() -> None:
    """9차 new3: '가게 주인이 그때 본 일을 설명하고'인데 문제에 그 말이 없음."""
    assert "MISSION_TESTIMONY" in investigate_codes(
        "가게 주인이 그때 본 일을 설명하고, 게시글도 봐요."
    )
    assert "MISSION_TESTIMONY" not in investigate_codes("게시글을 함께 살펴봐요.")


# ---------------------------------------------------------------- 5. 11차 치명 결함 종류(나)
def test_day_step_yesterday_must_have_happened() -> None:
    """11차 way3b: 수요일 '어제 포장 끈이 날아간 쪽', 화요일에 포장 끈이 없음."""
    theme = theme_of("ROUTE")
    theme["days"][2]["dayStep"] = "어제 포장 끈이 날아간 쪽도 살피려고 화단에 왔어."
    assert "어제 없던 일" in " ".join(checks.v12_problems(theme))
    theme["days"][1]["clue"] = "포장 끈이 바람에 날아가는 걸 내가 봤어!"
    assert "어제 없던 일" not in " ".join(checks.v12_problems(theme))
    # '어제 들은 걸'처럼 한 일만 말하면 봄 밖(코드 대신 문장 꼴)
    theme["days"][2]["dayStep"] = "어제 들은 걸 떠올리며 화단으로 와 봤어."
    assert "어제 없던 일" not in " ".join(checks.v12_problems(theme))


def test_secret_ingredient_event_name_stays_the_same() -> None:
    """11차 hand5: 시작 '토요일 잔치에 낼 떡' ↔ 단서 '대회에 낼 할머니 떡'."""
    theme = theme_of("SECRET_INGREDIENT", intro="아린은 토요일 잔치에 낼 할머니 떡을 받았어.")
    theme["days"][0]["clue"] = "할머니가 대회에 낼 떡 재료를 방앗간에서 사는 걸 내가 봤어!"
    got = [r for r in checks.v12_problems(theme) if r.startswith("EVENT_NAME")]
    assert got and "MON clue" in got[0] and "'잔치'와" in got[0]
    assert checks.fix_targets(got) == {"MON.clue": got}
    theme["days"][0]["clue"] = "할머니가 잔치에 낼 떡 재료를 방앗간에서 사는 걸 내가 봤어!"
    assert not [r for r in checks.v12_problems(theme) if r.startswith("EVENT_NAME")]
    # '장터'는 장소 뜻으로도 써 보지 않음(11차 hand4b '장터도 살펴보려 해')
    theme["days"][1]["dayStep"] = "사장님이 재료를 사러 다닌 장터도 살펴보려 해."
    assert not [r for r in checks.v12_problems(theme) if r.startswith("EVENT_NAME")]


# ---------------------------------------------------------------- 6. 소리 탐정 약속 감각(12차)
def test_story_day_sense_follows_last_clause() -> None:
    """사건 단서 날은 마지막 말(알려 주는 사실)이 소리 이야기일 때만 들은 날(HEARD_END)."""
    theme = ask_theme()
    d = checks.theme_day(theme, "MON")
    d["condition"] = {"kind": "STORY", "feature": "", "allowed": []}
    cases = {
        # 12차 snd5b: '이어졌어'도 소리 이야기
        "내가 들었어. 그 밤, 이웃집 불이 켜진 뒤 소리가 다시 이어졌어!": "HEARD",
        # 13차 snd3b: '흔들렸어'의 '들렸'은 들은 말이 아님
        "내가 본 흰 커튼 끝은 그 밤 소리가 날 때 살짝 흔들렸어!": "SEEN",
        # 13차 snd5: 앞말 '들은'이 있어도 알려 주는 사실은 본 것
        "내가 들은 그 밤, 소리가 난 뒤 복도 종이 장식이 천천히 흔들렸어!": "SEEN",
        "내가 본 할머니가 그릇을 옮길 때 소리가 났어!": "HEARD",
    }
    for clue, sense in cases.items():
        d["clue"] = clue
        assert checks.promise_sense(theme, d) == (sense, None), clue


def test_sound_feature_clue_must_be_heard() -> None:
    """12차 snd4: '내가 직접 본 소리 난 곳은' — 소리 특징 단서는 들은 것으로(SOUND_SEEN 칸
    고쳐 쓰기)."""
    theme = theme_of("SOUND")
    theme["features"] = [{"name": "소리 난 곳", "values": []}]
    mon = theme["days"][0]
    mon["condition"] = {"kind": "RULE", "feature": "소리 난 곳", "allowed": ["지붕 위"]}
    mon["evidence"] = {"kind": "SIGHTING", "when": "그때"}
    mon["clue"] = "내가 직접 본 소리 난 곳은 쓰레기통 둘레가 아니었어!"
    got = [r for r in checks.v12_problems(theme) if r.startswith("SOUND_SEEN")]
    assert got and checks.fix_targets(got) == {"MON.clue": got}
    mon["clue"] = "내가 들은 소리가 난 곳은 쓰레기통 둘레가 아니었어!"
    assert not [r for r in checks.v12_problems(theme) if r.startswith("SOUND_SEEN")]
    # 기록 날(영상·녹음)은 봄 밖, '흔들어 보니'는 본 것이 아님
    mon["clue"] = "내 영상에 찍힌 소리 난 곳은 쓰레기통 둘레가 아니었어!"
    mon["evidence"] = {"kind": "RECORD", "when": "그때"}
    assert not [r for r in checks.v12_problems(theme) if r.startswith("SOUND_SEEN")]
    mon["evidence"] = {"kind": "TRACE", "when": "그때"}
    mon["clue"] = "맡겨지기 전에 내가 흔들어 보니 달각 소리는 아니었어!"
    assert not [r for r in checks.v12_problems(theme) if r.startswith("SOUND_SEEN")]
