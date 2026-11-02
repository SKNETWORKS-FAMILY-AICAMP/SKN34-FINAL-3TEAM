"""#209 core HTTP 저장 설정 → report 생성/파일 검증용 보조 실행기.

ReportTemplateHttpIntegrationTest가 만든 격리 core에만 연결한다.
학습 기록·AI 서술·파일 저장소는 합성이며 실제 PG/LLM/S3를 호출하지 않는다.
report-service 가상환경 Python으로 실행한다.
"""

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/report-service"))

from app.clients.ai_client import NarrativeResponse
from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.generation.narrative_generator import NarrativeGenerator
from app.generation.pipeline import NamedGenerator
from app.generation.records import EvidenceRecord
from app.rendering.generator import RenderingGenerator
from app.rendering.renderer import ReportRenderer
from app.security import UserContext, bind_user_context, reset_user_context
from tests.render_helpers import fixed_result
from tests.report_helpers import command_for
from tests.test_narrative import Previous
from tests.test_rendering import pdf_text


async def verify(core_url: str, student: UUID, private: bool = False):
    report, source = fixed_result(student)
    bodies = {}
    sent = []

    class Ai:
        async def narrative(self, payload):
            sent.append(payload)
            return NarrativeResponse.model_validate(
                {
                    "narrative": {
                        "text": "답변 제출 시도 1건이 확인되었습니다.",
                        "source": "LLM",
                        "modelExplanation": None,
                    },
                    "eveningQuestion": "어떤 까닭을 더 떠올렸니?",
                    "citedQuotes": [],
                    "versions": {"prompt": "synthetic@1", "model": "synthetic@1"},
                }
            )

    class Learning:
        async def evidence(self, student_id, links):
            return tuple(
                EvidenceRecord(
                    link.answer_id,
                    link.attempt_id,
                    link.answer_version,
                    item.payload["text"],
                    True,
                )
                for item in source.items
                if item.type.value == "QUOTE"
                for link in item.evidence
            )

    class Storage:
        def put(self, key, body, content_type):
            bodies[key] = body

        def delete_prefix(self, prefix):
            for key in list(bodies):
                if key.startswith(prefix):
                    del bodies[key]

    previous = Previous(source)
    if private:
        from app.generation.record_generator import RecordGenerator
        from tests.record_helpers import attempt_for, records_for

        class Records:
            async def records(self, student_id, period):
                return replace(
                    records_for(
                        student_id,
                        [
                            attempt_for(
                                student_id, texts=("합성비밀 첫답", "합성비밀 새답")
                            )
                        ],
                    ),
                    period=period,
                )

        previous = RecordGenerator(Records())
    token = bind_user_context(UserContext(None, "SYSTEM", frozenset([str(student)])))
    try:
        async with internal_client(core_url) as client:
            provider = CoreClient(client)
            pipeline = NamedGenerator(
                provider,
                RenderingGenerator(
                    NarrativeGenerator(previous, Ai(), Learning()),
                    ReportRenderer(),
                    Storage(),
                ),
            )
            result = await pipeline.generate(
                replace(command_for(student), narrative_enabled=True), report
            )
        assert result.versions["template"]["revision"] == 1
        assert result.versions["template"]["settings"]["tone"] == "EASY"
        assert not sent if private else sent[0]["tone"] == "EASY"
        assert (
            result.verification["numbersMatched"]
            and result.verification["quotesMatched"]
        )
        assert (
            result.narrative is None if private else result.narrative["source"] == "LLM"
        )
        assert len(bodies) == 6
        for key, body in bodies.items():
            text = pdf_text(body) if key.endswith("/pdf") else body.decode()
            assert "[강조]" in text
            assert "합성비밀" not in text
            if private or "/free/" in key:
                assert "답변제출시도1건이확인되었습니다." not in "".join(text.split())
            else:
                assert "답변제출시도1건이확인되었습니다." in "".join(text.split())
        assert "template" not in source.versions
        print(
            json.dumps(
                {
                    "coreHttp": True,
                    "templateRevision": 1,
                    "tone": "EASY",
                    "private": private,
                    "renderedFiles": len(bodies),
                    "numbersMatched": True,
                    "quotesMatched": True,
                    "synthetic": ["learning", "AI narrative", "object storage"],
                }
            )
        )
    finally:
        reset_user_context(token)


if __name__ == "__main__":
    asyncio.run(
        verify(
            sys.argv[1],
            UUID(sys.argv[2]),
            len(sys.argv) > 3 and sys.argv[3] == "private",
        )
    )
