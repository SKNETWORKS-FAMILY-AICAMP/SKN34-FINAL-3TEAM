"""주간 테마 초안 LangGraph (class-diagram 5.5, #437). 지금은 글 단계까지.

START → retrieve(#470 자리) → plan_theme → check_theme
  check_theme: 실패·상한 전 → plan_theme / 끝내 실패 → END(failure THEME)
               / 통과 → generate_mission ×5 (Send, 요일마다 생성·검사·미션 검토)
→ missions_done: 실패 요일 → END(failure MISSION) / 통과 → generate_dialogue ×5 (Send)
→ review_story: PASS·끝내 FAIL → END / 형식 오류 → review_story
                / 이야기 틀·단서 → plan_theme / 문제·낱말 → generate_mission(그 요일)
그림·영상·움직임(generate_images → review_images → generate_videos → review_videos
→ generate_motion)은 다음 단계에서 review_story 뒤에 붙인다.
"""

from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from app.theme_draft.nodes import ThemeContext, ThemeState
from app.theme_draft.nodes.dialogue import generate_dialogue
from app.theme_draft.nodes.mission import generate_mission
from app.theme_draft.nodes.plan import check_theme_node, plan_theme, retrieve
from app.theme_draft.nodes.review import review_story


def mission_sends(state: ThemeState) -> list[Send]:
    first = state.get("request_seed") or {}
    seed = state.get("mission_seed") or {}
    return [
        Send(
            "generate_mission",
            {"day": d, "theme": state["theme"], "seed": [*first.get(d, []), *seed.get(d, [])]},
        )
        for d in state["days_todo"]
    ]


def after_check(state: ThemeState) -> list[Send] | str:
    if state.get("failure"):
        return END
    if state.get("plan_bad"):
        return "plan_theme"
    return mission_sends(state)


async def missions_done(state: ThemeState) -> ThemeState:
    failures = state.get("mission_failures") or {}
    bad = [f"{d} {r}" for d in state["days_todo"] for r in failures.get(d) or []]
    return {"failure": {"stage": "MISSION", "reasons": bad}} if bad else {}


def after_missions(state: ThemeState) -> list[Send] | str:
    if state.get("failure"):
        return END
    return [
        Send(
            "generate_dialogue",
            {"day": d, "theme": state["theme"], "draft": state["drafts"][d]},
        )
        for d in state["days_todo"]
    ]


def after_review(state: ThemeState) -> list[Send] | str:
    route = state.get("review_route")
    if route == "AGAIN":
        return "review_story"
    if route == "PLAN":
        return "plan_theme"
    if route == "DAYS":
        return mission_sends(state)
    return END  # PASS·FAIL


@lru_cache
def build_graph() -> CompiledStateGraph:
    graph = StateGraph(ThemeState, context_schema=ThemeContext)
    graph.add_node("retrieve", retrieve)
    graph.add_node("plan_theme", plan_theme)
    graph.add_node("check_theme", check_theme_node)
    graph.add_node("generate_mission", generate_mission)
    graph.add_node("missions_done", missions_done)
    graph.add_node("generate_dialogue", generate_dialogue)
    graph.add_node("review_story", review_story)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "plan_theme")
    graph.add_edge("plan_theme", "check_theme")
    graph.add_conditional_edges("check_theme", after_check, ["plan_theme", "generate_mission", END])
    graph.add_edge("generate_mission", "missions_done")
    graph.add_conditional_edges("missions_done", after_missions, ["generate_dialogue", END])
    graph.add_edge("generate_dialogue", "review_story")
    graph.add_conditional_edges(
        "review_story", after_review, ["review_story", "plan_theme", "generate_mission", END]
    )
    return graph.compile(name="theme_draft")
