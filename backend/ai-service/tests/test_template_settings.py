import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.analysis_agent.template_settings import (
    TemplateProposal,
    TemplateProposalRequest,
    TemplateSettings,
    propose_template,
)
from app.errors import ApiError
from app.llm.base import LlmUnavailable


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"settings": {}, "clarification": "질문"},
        {"clarification": " "},
        {"settings": {"showOriginalText": True}},
        {"settings": {"sectionOrder": ["quotes"]}},
        {"settings": {"highlightMetrics": ["SCORE"]}},
    ],
)
def test_invalid_model_result_is_rejected(payload):
    with pytest.raises(ValidationError):
        TemplateProposal.model_validate(payload)


def test_proposal_has_no_records_and_uses_structured_result():
    class Llm:
        async def generate(self, **kwargs):
            assert kwargs["output"] is TemplateProposal
            assert kwargs["call_type"] == "ANALYSIS"
            assert "학생 원문 공개는 학생 본인의" in kwargs["system"]
            assert "studentId" not in kwargs["user"]
            return SimpleNamespace(data=TemplateProposal(settings=TemplateSettings(tone="CONCISE")))

    result = asyncio.run(
        propose_template(
            TemplateProposalRequest(question="간결하게", current=TemplateSettings()), Llm()
        )
    )
    assert result.settings.tone == "CONCISE"


def test_llm_failure_is_not_a_successful_proposal():
    class Llm:
        async def generate(self, **kwargs):
            raise LlmUnavailable("TIMEOUT", True)

    with pytest.raises(ApiError):
        asyncio.run(
            propose_template(
                TemplateProposalRequest(question="간결하게", current=TemplateSettings()), Llm()
            )
        )
