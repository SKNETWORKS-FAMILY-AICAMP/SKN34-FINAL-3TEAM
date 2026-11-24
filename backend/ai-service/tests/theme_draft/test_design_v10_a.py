"""#782 설계 v10 A(약속 줄·같은 주 안의 같은 말).

#971: 부탁 날이 이어 가기 날로 바뀌며 약속 줄 검사(ASK_PROMISE)·약속 감각(promise_sense)·코드 대신
약속 문장(PROMISE_FALLBACK, put_promise)·단서를 고친 뒤 약속만 다시 만들기를 뺐다. 그 시험은 지우고
남은 대화 흐름 시험과 다른 시험이 쓰는 도우미만 둔다.
- 같은 주 같은 말 다시 만들기(dedupe_dialogues)는 설계 v11에서 뺌
"""

import copy
from typing import Any

from app.theme_draft import checks
from app.theme_draft.graph import build_graph
from app.theme_draft.models import GeneratedLine
from tests.theme_draft.fixtures import dialogue, valid_theme
from tests.theme_draft.test_graph import gen_llm, review_llm, run

GRADE = 3
# 기본 요청(request_body)의 미션 방식 배정(test_graph.WAYS와 같음)
WAYS = {
    "MON": checks.FOLLOW,
    "TUE": checks.INVESTIGATE,
    "WED": checks.FOLLOW,
    "THU": checks.FOLLOW,
    "FRI": checks.FOLLOW,
}


def ask_theme() -> dict[str, Any]:
    """기본 요청의 미션 방식을 넣은 줄거리(다음 행동 종류 칸은 없음 — 예전 저장본처럼 다음 행동
    검사는 하지 않음)."""
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
    """그 요일 대화 셋째 줄을 text로 바꾼 대화."""
    lines = [x.model_dump() for x in dialogue(day).lines]
    lines[2]["text"] = text
    return lines


def test_graph_other_reason_still_omits_day() -> None:
    """끝내 남은 사유(화자)가 있으면 그 요일 대화를 빼고 경고(#971: 코드 대신 약속 문장 없음)."""
    bad = [GeneratedLine(speaker="할머니", text="여기야.")] * 4
    gen = gen_llm(dlg=lambda n, d: dialogue(d, lines=bad) if d == "MON" else dialogue(d))
    response = run(gen, review_llm())
    assert [d.day for d in response.dialogues] == ["TUE", "WED", "THU", "FRI"]
    reasons = [w.reason for w in response.warnings if (w.stage, w.item) == ("DIALOGUE", "MON")]
    assert reasons and not any(r.startswith("PROMISE_FALLBACK") for r in reasons)


def test_graph_dialogue_goes_straight_to_review() -> None:
    """#782 설계 v11: 같은 주 같은 말을 다시 만들던 dedupe_dialogues는 뺌(v9처럼)."""
    edges = {(e.source, e.target) for e in build_graph().get_graph().edges}
    assert ("generate_dialogue", "review_story") in edges
    assert "dedupe_dialogues" not in set(build_graph().get_graph().nodes)
