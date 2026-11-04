"""분석 답변 프롬프트의 원문 표시 형식."""

import json

from app.analysis_agent.calculators import compute
from app.analysis_agent.models import AnalysisRequest
from app.analysis_agent.prompts import build_answer_user
from tests.analysis_agent.records_fixture import PERIOD, REVISED, SCOPE, STUDENT, records


def request() -> AnalysisRequest:
    return AnalysisRequest.model_validate(
        {
            "conversationId": "c-1",
            "question": "되묻기 후 어떻게 달라졌어?",
            "scope": {"studentId": STUDENT, **PERIOD},
        }
    )


def test_sources_keep_title_and_text_in_separate_fields_without_numbers() -> None:
    # 번호·미션 제목이 글과 한 줄에 붙어 있으면 LLM이 인용에 함께 넣거나 번호를 답에 옮김
    computation = compute("CHANGES", records(), SCOPE)
    user = build_answer_user(request(), "CHANGES", computation)
    block = user.split("[원문]\n", 1)[1].split("\n[이전 대화]", 1)[0]
    sources = json.loads(block)
    assert {"미션": "쉬는 시간 토론", "글": REVISED} in sources
    assert all(set(source) == {"미션", "글"} for source in sources)
    assert "S1" not in user


def test_no_sources_marked_empty() -> None:
    computation = compute("COUNT", records(empty=True), SCOPE)
    assert "[원문]\n(없음)\n" in build_answer_user(request(), "COUNT", computation)
