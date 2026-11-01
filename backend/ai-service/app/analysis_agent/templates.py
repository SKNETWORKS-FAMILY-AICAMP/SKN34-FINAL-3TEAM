"""코드로 만드는 답변 문장. LLM 없이 계산 결과·원문만 옮김.

- 규칙 응답 모드 (P16): 대조 실패·LLM 장애
- 기록 부족 안내 (FN-AGT-09): 조회한 기록 수와 분석 가능 범위만, 능력 해석 없음
- 제공하지 않는 질문 안내 (FN-AGT-12): 물어볼 수 있는 범위
"""

from app.analysis_agent.calculators import Computation
from app.analysis_agent.models import Evidence, FallbackReason, Intent, Metric, Scope

QUOTE_CHARS = 60  # 규칙 응답에 싣는 원문 길이
QUOTE_LIMIT = 5
AVAILABLE = "숫자, 생각 유형별 활동, 아이가 쓴 생각, 되묻기 전후 변화, 돌아보기"


def fallback_answer(reason: FallbackReason, computation: Computation, scope: Scope) -> str:
    head = {
        "VERIFICATION_FAILED": (
            "AI 답변의 숫자·인용을 기록과 맞춰 보지 못해, 계산한 수치와 원문만 보여 드려요."
        ),
        "AI_UNAVAILABLE": "지금은 AI 답변을 만들 수 없어, 계산한 수치와 원문만 보여 드려요.",
    }[reason]
    lines = [head, _period(scope), *(f"- {metric_line(m)}" for m in computation.metrics)]
    quotes = fallback_evidence(computation)
    if quotes:
        lines.append("아이가 쓴 글:")
        lines += [f"- {e.mission_title}: 「{e.quote}」" for e in quotes]
    return "\n".join(lines)


def fallback_evidence(computation: Computation) -> list[Evidence]:
    return [
        source.evidence.model_copy(update={"quote": source.text[:QUOTE_CHARS]})
        for source in computation.sources[:QUOTE_LIMIT]
    ]


def insufficient_answer(kind: str, computation: Computation, scope: Scope) -> str:
    count = computation.record_count
    reason = {
        "NO_RECORD": "이 기간에 답변을 제출한 시도가 없어 분석할 기록이 없어요.",
        "NO_CHANGES": f"답변을 제출한 시도 {count}개 중 되묻기 뒤에 답변을 다시 쓴 시도가 없어 "
        "전후를 비교할 수 없어요.",
        "NO_REFLECTIONS": f"답변을 제출한 시도 {count}개 중 돌아보기를 쓴 시도가 없어요.",
    }[kind]
    return f"{_period(scope)} {reason} 기간을 넓히거나 다른 내용을 물어봐 주세요."


def unsupported_answer(intent: Intent, computation: Computation, scope: Scope) -> str:
    head = (
        "수학 풀이 점검은 아직 제공하지 않아요."
        if intent == "MATH_CHECK"
        else "이 질문은 학습 기록으로 답할 수 없어요."
    )
    return (
        f"{head} {_period(scope)} 답변을 제출한 시도는 {computation.record_count}개예요. "
        f"{AVAILABLE}에 대해 물어봐 주세요."
    )


def metric_line(metric: Metric) -> str:
    if not metric.is_ratio:
        return f"{metric.label}: {metric.count}개"
    if metric.denominator == 0:
        return f"{metric.label}: 해당하는 시도가 없어요"
    line = f"{metric.label}: {metric.denominator}개 중 {metric.numerator}개"
    if metric.value is None:
        return f"{line} (기록이 적어 비율은 표시하지 않아요)"
    return f"{line} ({metric.value * 100:.0f}%)"


def _period(scope: Scope) -> str:
    return f"조회 기간은 {scope.from_.isoformat()}부터 {scope.to.isoformat()}까지예요."
