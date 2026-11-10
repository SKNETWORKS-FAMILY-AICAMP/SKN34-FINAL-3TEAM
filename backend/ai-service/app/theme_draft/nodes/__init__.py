"""주간 테마 초안 그래프 노드 공통: 상태·실행 컨텍스트·피드백 나누기 (class-diagram 5.5).

요일별 노드(미션·대화)는 Send로 병렬 실행되므로 요일 키로 합쳐지는 상태 칸은 사전 합치기
reducer를 쓴다. 요일 값이 빈 목록·None이면 '그 요일 문제 없음'이다
(다시 만들어 통과하면 이전 값을 지운다).
"""

import operator
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from app.config import Settings
from app.llm.base import LlmClient
from app.llm.media import ImageClient, VideoClient
from app.mission_draft.models import Draft, Failure
from app.mission_draft.service import MissionDraftService
from app.prompt_versions.models import PromptChoice
from app.theme_draft.models import ThemeDraftRequest
from app.theme_draft.storage import ThemeStorage, new_run_id

THEME_CALL_TYPE = "THEME_DRAFT"  # 글 생성·검토 사용량 (api-spec 4.6)
# 기존 미션 초안 장치(FAILURE_FIX·CHECK_FIX)가 아는 검사. learning 검사 실패(previousFailures
# MISSION)도 여기로
EXISTING_MISSION_CHECKS = {
    "REQUIRED",
    "QUESTION_LENGTH",
    "LEAK",
    "STANDARD_CODE",
    "ELEMENT_CODE",
    "SHAPE",
}


def merge(old: dict | None, new: dict | None) -> dict:
    return {**(old or {}), **(new or {})}


class ThemeState(TypedDict, total=False):
    plan_feedback: list[tuple[str, list[str]]]  # 줄거리 다시 만들 때 넣는 (단계, 사유)
    plan_attempts: int
    plan_bad: list[str]
    theme: dict[str, Any] | None  # GeneratedTheme.model_dump()
    days_todo: list[str]  # 이번에 미션·대화를 (다시) 만들 요일
    request_seed: dict[str, list[str]]  # 요청 previousFailures의 MISSION 사유(요일별, 매번 넣음)
    image_seed: dict[
        str, list[str]
    ]  # 요청 previousFailures의 IMAGE 사유(그림 이름별, "*"는 모든 그림)
    mission_seed: dict[str, list[str]]  # 글 검토가 요일을 다시 보낼 때 넣는 사유
    drafts: Annotated[dict[str, Draft], merge]
    mission_failures: Annotated[dict[str, list[str]], merge]
    mission_warnings: Annotated[dict[str, list[str]], merge]
    dialogues: Annotated[dict[str, list[dict] | None], merge]
    dialogue_omitted: Annotated[dict[str, list[str]], merge]
    review_runs: int
    review_reasons: list[str]  # 마지막 검토 FAIL 사유
    review_route: str  # PASS·FAIL·AGAIN(형식만 틀림)·PLAN(줄거리부터)·DAYS(그 요일 미션·대화)
    review_warnings: list[dict]
    failure: dict | None
    # 그림·영상·움직임(review_story PASS 뒤 차례로 실행)
    outfit_image: bytes  # 테마 옷 뭉치(모든 그림의 첫 참조)
    scene_images: dict[str, bytes]  # MON~FRI 미션 그림, INTRO1~4·OUTRO1~4 컷 첫 그림(통과한 것만)
    image_keys: dict[str, str]  # 장면 → S3 키(INTRO·OUTRO는 4번째 컷 첫 그림)
    video_skip: list[str]  # 컷 그림이 끝내 실패해 영상을 만들지 않을 장면(INTRO·OUTRO)
    video_keys: dict[str, str]
    motions: dict[str, dict]  # 장면 → ThemeMotion 모양
    media_warnings: Annotated[list[dict], operator.add]  # {stage, item, reason}


@dataclass
class ThemeContext:
    request: ThemeDraftRequest
    settings: Settings
    llm: LlmClient  # 테마 생성 모델
    review_llm: LlmClient  # 생성과 다른 검토 모델
    missions: MissionDraftService  # 미션 생성은 미션 초안 재사용(테마 생성 모델로)
    prompt: PromptChoice  # themeDraft
    deadline: float
    clock: Callable[[], float] = field(default=time.monotonic)
    knowledge: dict[str, list[str]] | None = None  # #470 근거 자리(요일별), 지금은 비움
    image: ImageClient | None = None  # 없으면(버킷·키 없음) 그림·영상·움직임을 건너뜀
    video: VideoClient | None = None  # 없으면(THEME_VIDEO_ENABLED=false) 영상만 건너뜀
    storage: ThemeStorage | None = None
    run_id: str = field(default_factory=new_run_id)  # S3 theme-drafts/{run_id}/
    mungchi: bytes = b""  # 기본 뭉치 그림(assets/mungchi-2d.png)

    @property
    def grade(self) -> int:
        return self.request.grade

    def can_regenerate(self) -> bool:
        """다음 다시 생성을 시작할 시간이 남았는지(마감까지 theme_min_regen_seconds 이상)."""
        return self.deadline - self.clock() >= self.settings.theme_min_regen_seconds


DEADLINE_REASON = "DEADLINE 마감까지 남은 시간이 부족해 다시 생성하지 않음"


def uniq(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def split_mission_feedback(reasons: list[str]) -> tuple[list[Failure], list[str]]:
    """'<검사 코드> <자세히>' 사유 → (미션 초안 previous_failures, 테마 부분에 덧붙일 문장)."""
    existing, theme = [], []
    for reason in reasons:
        check, _, rest = reason.partition(" ")
        if check in EXISTING_MISSION_CHECKS:
            existing.append(Failure(check=check, reason=rest.split()[0] if rest.strip() else check))
        else:
            theme.append(reason)
    return existing, uniq(theme)
