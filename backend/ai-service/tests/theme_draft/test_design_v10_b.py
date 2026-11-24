"""#782 설계 v10 B(돕는 사람·쓰임): 일 → 사람 → 쓰임 → 장소를 모델이 정하고 코드·검토가 지킨다.
#971에서 부탁 날 일 틀·쓰임 시험은 지움(이어 가기 날은 일 틀이 없고 쓰임은 쓴 글을 읽을 사람 날만).
오늘 온 까닭 규칙(1.4)은 설계 v11에서 뺌.

- helperUse(국어 부탁 날 아이 답의 쓰임, 내부 칸): 응답에 안 나옴, 비면 REQUIRED(칸 고쳐 쓰기)
- USE_MISSING 쓰임 낱말은 helperUse의 마지막 '에·에다·으로·로' 앞 말에서, 예전 저장본은 dayFrames
- HELPER_SAME은 배정 호칭을 보지 않음(같은 주 같은 사람·등장인물만)
- review_helpers(돕는 사람 검토)는 설계 v11에서 뺌(v9처럼 줄거리 통과 뒤 곧바로 미션)
"""

import copy
import random
from typing import Any

from app.theme_draft import checks, prompts
from tests.theme_draft.fixtures import (
    valid_theme,
)
from tests.theme_draft.helpers import request_body

GRADE = 3
KOREAN_MON = "4국05-02"
USE = "공원 소식 모음에 실을게"


def korean_frames() -> dict[str, dict[str, Any]]:
    return checks.day_frames(
        [("MON", [KOREAN_MON], "ANALYZE")], {"MON": checks.FOLLOW}, random.Random(0)
    )


def korean_theme(**mon: Any) -> dict[str, Any]:
    """월요일만 국어 부탁 날(dayFrames 일 틀)인 테마."""
    theme = copy.deepcopy(valid_theme())
    theme["dayFrames"] = korean_frames()
    checks.theme_day(theme, "MON").update(missionWay=checks.FOLLOW, **mon)
    return theme


def korean_body() -> dict[str, Any]:
    """월요일(ANALYZE)에만 국어 성취기준을 더한 요청(미션 방식·증거 배정은 기본 요청과 같고, 특징
    표의 성취기준 코드 4과02-02도 그대로 있음)."""
    body = request_body()
    for m in body["missions"]:
        if m["thinkingType"] == "ANALYZE":
            m["standards"].append({"code": KOREAN_MON, "statement": "작품 감상"})
    return body


# ---------------------------------------------------------------- 내부 칸·REQUIRED
# ---------------------------------------------------------------- 쓰임 낱말
def test_use_words_come_from_before_the_last_particle() -> None:
    assert checks.use_words("책 추천 카드에 붙일게") == ["추천", "카드"]
    assert checks.use_words("소식지에 실을게") == ["소식지"]
    assert checks.use_words("안내판·방송 글로 쓸게") == ["안내판", "방송"]
    assert checks.use_words("시집 뒤 감상 칸에다 붙일게") == ["시집", "감상"]
    assert checks.use_words("새 팻말 안내문으로 걸게") == ["팻말", "안내문"]
    # 마지막 조사 기준(앞의 '줄로'에서 자르지 않음), '에게'는 조사 '에'가 아님. 합칠 때: 동사·조사가
    # 붙은 말('줄로'·'정리해'·'손님들에게')은 쓰임 낱말에서 뺌(흔한 말로 통과하지 않게)
    assert checks.use_words("두 줄로 정리해 게시판에 붙일게") == ["게시판"]
    assert checks.use_words("손님들에게 보여 줄 게시판") == ["보여", "게시판"]
    assert checks.use_words("") == []


# ---------------------------------------------------------------- 돕는 사람
def test_review_helpers_node_is_removed() -> None:
    """#782 설계 v11: 돕는 사람 검토(review_helpers, 테마마다 검토 호출 +1)는 뺌 — 줄거리 통과 뒤
    곧바로 요일 미션(v9). 억지는 미션 검토 STORY_LINK·글 검토·측정 판정이 봄."""
    from app.theme_draft import models
    from app.theme_draft.graph import build_graph
    from app.theme_draft.nodes import plan

    nodes = set(build_graph().get_graph().nodes)
    assert "review_helpers" not in nodes
    assert not hasattr(plan, "review_helpers") and not hasattr(models, "GeneratedHelperReview")
    assert not hasattr(prompts, "HELPER_REVIEW_SYSTEM")
    edges = {(e.source, e.target) for e in build_graph().get_graph().edges}
    assert ("check_theme", "generate_mission") in edges
