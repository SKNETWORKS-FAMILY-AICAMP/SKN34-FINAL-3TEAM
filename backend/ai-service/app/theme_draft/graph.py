"""주간 테마 초안 LangGraph (class-diagram 5.5, #437).

START → retrieve(#470 자리) → plan_theme → check_theme
  check_theme: 칸 하나만 고치면 되는 사유뿐 → fix_theme → check_theme
               / 실패·상한 전 → plan_theme / 끝내 실패 → END(failure THEME)
               / 통과 → generate_mission ×5 (Send, 요일마다 생성·검사·미션 검토)
               (요일마다 미션이 통과하면 그 요일 수사 연결 문장을 문제 소재에 맞게 고쳐 씀, #535)
→ missions_done(고친 수사 연결 문장을 테마에 넣음): 실패 요일 → END(failure MISSION)
  / 통과 → generate_dialogue ×5 (Send)
→ review_story: 끝내 FAIL → END / 형식 오류 → review_story
                / 약속 줄만 틀림(#782 설계 v12) → generate_dialogue(그 요일만) → review_story
                / 단서 논리만(처음 한 번) → fix_clues(그 요일 단서만 고쳐 씀) → review_story
                  (고친 단서가 코드 검사에 걸리면 plan_theme, 약속 감각이 바뀌어 약속이 틀린
                  요일은 generate_dialogue → review_story)
                / 이야기 틀·단서 → plan_theme / 문제·낱말 → generate_mission(그 요일)
                / PASS → generate_images
→ generate_images(그림마다 검토 포함): 설정 없음·미션 그림 끝내 실패 → END / 통과 → generate_videos
→ generate_videos(컷마다 검토 포함, 꺼져 있으면 경고만) → generate_motion → END

부분 다시 생성(#537): START → restore(원래 결과·재료 그림 되살림)
  → 미션 대상이 있으면 generate_mission(그 요일만)부터, 없으면 generate_images부터.
  노드는 그대로 쓰고
  그림·영상·움직임 노드는 redo_* 범위만 다시 만든다. 글 검토가 줄거리·단서·대상 밖 요일을 고치라고
  하면 failure REVIEW로 끝낸다(사용자 결정 2026-11-17).
"""

from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from app.theme_draft.nodes import ThemeContext, ThemeState
from app.theme_draft.nodes.dialogue import generate_dialogue
from app.theme_draft.nodes.images import generate_images
from app.theme_draft.nodes.mission import apply_hooks, generate_mission
from app.theme_draft.nodes.motion import generate_motion
from app.theme_draft.nodes.plan import (
    check_theme_node,
    fix_clues,
    fix_helpers,
    fix_theme,
    plan_theme,
    retrieve,
)
from app.theme_draft.nodes.review import review_story
from app.theme_draft.nodes.video import generate_videos
from app.theme_draft.regen import restore


def start(state: ThemeState) -> str:
    return "restore" if state.get("partial") else "retrieve"


def after_restore(state: ThemeState) -> list[Send] | str:
    if state.get("failure"):
        return END
    return mission_sends(state) if state.get("days_todo") else "generate_images"


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
    if state.get("fix_targets"):
        return "fix_theme"
    if state.get("plan_bad"):
        return "plan_theme"
    return mission_sends(state)


async def missions_done(state: ThemeState) -> ThemeState:
    failures = state.get("mission_failures") or {}
    bad = [f"{d} {r}" for d in state["days_todo"] for r in failures.get(d) or []]
    if bad:
        return {"failure": {"stage": "MISSION", "reasons": bad}}
    theme = state["theme"]
    assert theme is not None
    fixed = apply_hooks(theme, state.get("hook_fixes") or {}, state["days_todo"])
    # #782 설계 v8: 미션 검토가 지문 탓으로 짚어 고친 그날 지문
    fixed = apply_hooks(
        fixed, state.get("material_fixes") or {}, state["days_todo"], "missionMaterial"
    )
    return {"theme": fixed} if fixed is not theme else {}


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


def talk_sends(state: ThemeState) -> list[Send]:
    """#782 설계 v12: 그 요일 대화만 다시(talk_seed 사유를 처음부터 넣음) → review_story."""
    return [
        Send(
            "generate_dialogue",
            {
                "day": d,
                "theme": state["theme"],
                "draft": state["drafts"][d],
                "seed": seed,
                # #782 설계 v13: 같은 주 약속 다시 만들기는 원래 대화가 맞으므로 실패하면 그대로 둠
                "keep": (state.get("dialogues") or {}).get(d) if state.get("talk_keep") else None,
            },
        )
        for d, seed in (state.get("talk_seed") or {}).items()
    ]


def after_fix_clues(state: ThemeState) -> list[Send] | str:
    if state.get("review_route") == "PLAN":
        return "plan_theme"
    return talk_sends(state) if state.get("talk_seed") else "review_story"


def after_fix_helpers(state: ThemeState) -> list[Send] | str:
    """#782 설계 v13: 돕는 사람·일 칸을 고친 요일 미션부터 다시(고친 칸이 검사에 걸리면
    줄거리부터)."""
    if state.get("review_route") == "PLAN":
        return "plan_theme"
    if state.get("review_route") == "REVIEW":  # 고쳐 쓰기 호출 실패 — 고치지 않고 글 검토로
        return "review_story"
    return mission_sends(state)


def after_review(state: ThemeState) -> list[Send] | str:
    route = state.get("review_route")
    if route == "AGAIN":
        return "review_story"
    if route == "PLAN":
        return "plan_theme"
    if route == "CLUE":
        return "fix_clues"
    if route == "HELPER":
        return "fix_helpers"
    if route == "TALK":
        return talk_sends(state)
    if route == "DAYS":
        return mission_sends(state)
    if route == "PASS":
        return "generate_images"
    return END  # FAIL


def after_images(state: ThemeState) -> str:
    """그림 설정이 없거나(그림 없음) 미션 그림이 끝내 실패하면 영상·움직임 없이 끝."""
    if state.get("failure") or not state.get("scene_images"):
        return END
    return "generate_videos"


@lru_cache
def build_graph() -> CompiledStateGraph:
    graph = StateGraph(ThemeState, context_schema=ThemeContext)
    graph.add_node("restore", restore)
    graph.add_node("retrieve", retrieve)
    graph.add_node("plan_theme", plan_theme)
    graph.add_node("check_theme", check_theme_node)
    graph.add_node("fix_theme", fix_theme)
    graph.add_node("generate_mission", generate_mission)
    graph.add_node("missions_done", missions_done)
    graph.add_node("generate_dialogue", generate_dialogue)
    graph.add_node("review_story", review_story)
    graph.add_node("fix_clues", fix_clues)
    graph.add_node("fix_helpers", fix_helpers)
    graph.add_node("generate_images", generate_images)
    graph.add_node("generate_videos", generate_videos)
    graph.add_node("generate_motion", generate_motion)

    graph.add_conditional_edges(START, start, ["restore", "retrieve"])
    graph.add_conditional_edges(
        "restore", after_restore, ["generate_mission", "generate_images", END]
    )
    graph.add_edge("retrieve", "plan_theme")
    graph.add_edge("plan_theme", "check_theme")
    graph.add_conditional_edges(
        "check_theme", after_check, ["fix_theme", "plan_theme", "generate_mission", END]
    )
    graph.add_edge("fix_theme", "check_theme")
    graph.add_edge("generate_mission", "missions_done")
    graph.add_conditional_edges("missions_done", after_missions, ["generate_dialogue", END])
    graph.add_edge("generate_dialogue", "review_story")
    graph.add_conditional_edges(
        "review_story",
        after_review,
        [
            "review_story",
            "fix_clues",
            "fix_helpers",
            "plan_theme",
            "generate_mission",
            "generate_dialogue",
            "generate_images",
            END,
        ],
    )
    graph.add_conditional_edges(
        "fix_clues", after_fix_clues, ["plan_theme", "generate_dialogue", "review_story"]
    )
    graph.add_conditional_edges(
        "fix_helpers", after_fix_helpers, ["plan_theme", "generate_mission", "review_story"]
    )
    graph.add_conditional_edges("generate_images", after_images, ["generate_videos", END])
    graph.add_edge("generate_videos", "generate_motion")
    graph.add_edge("generate_motion", END)
    return graph.compile(name="theme_draft")
