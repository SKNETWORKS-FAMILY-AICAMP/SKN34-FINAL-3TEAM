"""AI 품질 신호 카운터 (아키텍처 4.6, #1030).

판정 결과·분석 대체 응답·학생 응답 가드 차단을 센다. 속성은 정해진 코드값과 프롬프트 버전
문자열뿐이다. 원문·학생 ID·업무 ID(answerId·attemptId 등)는 넣지 않는다 (NFR-SEC-05).
provider가 없으면(OTEL_METRICS_EXPORTER 꺼짐·단위 시험 기본) no-op이다.
"""

from typing import Any, Literal

from app import tracing

JUDGMENT_RESULTS = "ai.judgment.results"
ANALYSIS_FALLBACKS = "ai.analysis.fallbacks"
GUARD_BLOCKED = "ai.guard.blocked"
NONE = "none"

Guard = Literal["followup_leak", "judgment_quote"]


def _judgment_results(meter: Any) -> Any:
    return meter.create_counter(
        JUDGMENT_RESULTS,
        unit="{judgment}",
        description="판정 응답 수 (결과·보류 이유·프롬프트 버전별)",
    )


def _analysis_fallbacks(meter: Any) -> Any:
    return meter.create_counter(
        ANALYSIS_FALLBACKS,
        unit="{fallback}",
        description="분석 대화 대체 응답(규칙 템플릿) 수 (이유별)",
    )


def _guard_blocked(meter: Any) -> Any:
    return meter.create_counter(
        GUARD_BLOCKED,
        unit="{block}",
        description="학생 응답 가드가 막은 수 (가드별)",
    )


def judgment_result(result: str, held_reason: str | None, prompt_version: str | None) -> None:
    """판정 응답 하나. 503(AI_UNAVAILABLE) 등 오류는 판정 결과가 아니라 부르지 않는다."""
    tracing.instrument(JUDGMENT_RESULTS, _judgment_results).add(
        1,
        {
            "result": result,
            "held_reason": held_reason or NONE,
            "prompt_version": prompt_version or NONE,
        },
    )


def analysis_fallback(reason: str) -> None:
    """실제로 만들어진 대체 응답 하나. 기록 부족·미지원 안내는 대체 응답이 아니라 부르지 않는다."""
    tracing.instrument(ANALYSIS_FALLBACKS, _analysis_fallbacks).add(1, {"reason": reason})


def guard_blocked(guard: Guard) -> None:
    """가드가 학생에게 갈 AI 출력 하나를 막음."""
    tracing.instrument(GUARD_BLOCKED, _guard_blocked).add(1, {"guard": guard})
