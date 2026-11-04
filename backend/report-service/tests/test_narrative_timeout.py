import asyncio

import httpx

from app.clients.ai_client import AiClient


def test_report_queue_wait_budget_does_not_change_other_internal_calls():
    async def run():
        seen = []

        def handler(request):
            seen.append(request.extensions["timeout"])
            return httpx.Response(
                200,
                json={
                    "narrative": {
                        "text": "가상 학습 기록입니다.",
                        "source": "LLM",
                        "modelExplanation": None,
                    },
                    "eveningQuestion": "어떤 생각이 기억에 남니?",
                    "citedQuotes": [],
                    "versions": {"prompt": "report@1", "model": "synthetic-gemma"},
                },
            )

        async with httpx.AsyncClient(
            base_url="http://ai.test", timeout=30, transport=httpx.MockTransport(handler)
        ) as client:
            await AiClient(client, timeout=130).narrative({})
            assert client.timeout.read == 30
        assert seen[0]["read"] == 130
        assert seen[0]["connect"] == 2

    asyncio.run(run())
