"""분석 대화 프롬프트와 LLM 출력 형식. 프롬프트를 바꾸면 PROMPT_VERSION을 올림.

LLM 호출은 두 번: 질문 분류·범위 확인(classify), 계산 결과를 문장으로 옮기기(answer, 스트리밍).
학생 이름·ID는 넣지 않음 (NFR-SEC-03). 시도·답변 ID·번호도 넣지 않고 원문은 미션 제목·글만 보여 줌.
answer는 일반 텍스트: 아이 글은 큰따옴표로 옮기고, 출처는 대조 단계가 따옴표 구간으로 찾음.
sLLM은 번호를 답에 옮기거나 제안 질문을 따옴표로 감싸 인용 대조에 걸리기 쉬움
→ 번호를 빼고 옳음·틀림 예시로 막음.
"""

import json

from app.analysis_agent.calculators import Computation
from app.analysis_agent.models import AnalysisRequest, Intent, ScopeIssue
from app.judgment.models import ApiModel

PROMPT_VERSION = "analysis@3"
HISTORY_TURNS = 6  # 맥락 파악에 쓰는 최근 이전 대화 수


class Classification(ApiModel):
    intent: Intent
    scope_issue: ScopeIssue


CLASSIFY_SYSTEM = """\
너는 초등학생 사고력 학습 서비스에서 학부모 질문을 분류하는 도우미다.
학부모는 이미 자녀 한 명과 조회 기간을 골라 둔 상태다. 질문 내용만 보고 아래를 정한다.

intent (하나만):
- COUNT: 몇 번·몇 개·얼마나 했는지 같은 숫자 질문
- THINKING_TYPES: 생각 유형(분석하기·따져 보기·새로 만들기·문제 해결하기·돌아보기)별 활동
- CHILD_THOUGHTS: 아이가 실제로 쓴 생각·답변 내용
- CHANGES: 되묻기(추가 질문)를 받은 뒤 답변이 어떻게 달라졌는지
- REFLECTIONS: 미션을 마치고 쓴 돌아보기·난이도
- MATH_CHECK: 수학 문제 풀이 점검
- OTHER: 학습 기록 분석과 관계없는 질문

scope_issue:
- NONE: 대상·기간을 따로 말하지 않았거나 골라 둔 범위와 맞음
- OTHER_CHILD: 다른 자녀(이름·형제 등)를 묻는 질문
- DIFFERENT_PERIOD: 골라 둔 기간과 다른 기간(지난달·작년·특정 날짜 등)을 묻는 질문
- UNCLEAR: 누구 또는 언제를 묻는지 판단할 수 없음
기간을 말하지 않은 후속 질문은 골라 둔 범위를 이어 쓰므로 NONE이다.
"""

ANSWER_SYSTEM = """\
너는 학부모에게 자녀의 학습 기록을 설명하는 도우미다. 아래 규칙을 반드시 지킨다.

1. 숫자는 [계산 결과]와 [기록 수]에 있는 값만, 아라비아 숫자로 쓴다 ("두 시도"가 아니라 "2개 시도").
   새로 계산하거나 어림하지 않는다. 비율이 null인 항목은 비율을 말하지 않고 개수만 말한다.
2. 아이의 글을 옮길 때는 [원문]의 "글" 값만 글자 그대로 큰따옴표로 감싼다.
   미션 제목을 따옴표 안에 넣거나 글 앞에 붙이지 않는다.
3. 따옴표(큰따옴표·작은따옴표·낫표)는 아이 글을 옮길 때만 쓴다.
   지표 이름·미션 제목·낱말을 강조하거나 집에서 나눌 질문을 적을 때 따옴표를 쓰지 않는다.
   옳음: 집에서 근거를 찾을 때 어떤 점이 어려웠는지 이야기해 보세요.
   틀림: 집에서 "근거를 찾을 때 어떤 점이 어려웠니?"라고 물어보세요.
4. 기록에서 보이는 사실만 말한다.
   레벨·등급·점수·사고력 같은 평가나 다른 아이와의 비교를 하지 않는다.
   기록이 적은 것을 능력 부족으로 해석하지 않는다.
5. 기간은 "이번 기간"이나 [조회 기간]의 날짜로만 말한다.
   "지난주"처럼 다른 기간으로 바꿔 말하지 않는다.
6. 한국어로만 답한다. 학부모에게 존댓말로 3~5문장 안에서 답한다.
   아이의 행동에는 높임말을 쓰지 않는다.
   마지막에 집에서 나눌 수 있는 대화 한 가지를 제안해도 된다.
7. 답변 문장만 일반 텍스트로 쓴다. JSON·제목·목록 기호를 쓰지 않는다.
"""


def build_classify_user(request: AnalysisRequest) -> str:
    return f"""\
[골라 둔 범위] {request.scope.from_.isoformat()} ~ {request.scope.to.isoformat()}
[이전 대화]
{_history(request)}
[질문]
{request.question}"""


def build_answer_user(request: AnalysisRequest, intent: Intent, computation: Computation) -> str:
    metrics = [
        {
            "label": m.label,
            "count": m.count,
            "numerator": m.numerator if m.is_ratio else None,
            "denominator": m.denominator if m.is_ratio else None,
            "ratio": None if m.value is None else f"{m.value * 100:.1f}%",
            "formula": m.formula,
        }
        for m in computation.metrics
    ]
    # 미션·글을 필드로 나눠, 인용할 때 제목이 글에 붙지 않게 함
    sources = [
        {"미션": source.evidence.mission_title, "글": source.text} for source in computation.sources
    ]
    return f"""\
[조회 기간] {request.scope.from_.isoformat()} ~ {request.scope.to.isoformat()}
[질문 유형] {intent}
[기록 수] 집계 대상 시도 {computation.record_count}개
[계산 결과]
{json.dumps(metrics, ensure_ascii=False, indent=1)}
[원문]
{json.dumps(sources, ensure_ascii=False, indent=1) if sources else "(없음)"}
[이전 대화]
{_history(request)}
[질문]
{request.question}"""


def _history(request: AnalysisRequest) -> str:
    turns = request.history[-HISTORY_TURNS:]
    if not turns:
        return "(없음)"
    return "\n".join(f"{'학부모' if t.role == 'USER' else '도우미'}: {t.text}" for t in turns)
