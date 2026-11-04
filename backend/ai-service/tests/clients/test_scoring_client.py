import asyncio
from typing import Any

import httpx
import pytest

from app.clients.scoring_client import ScoringClient, ScoringUnavailable

ESSAY = {
    "active": True,
    "inputType": "ESSAY",
    "scores": {"org": 2, "cont": 1, "exp": 3},
    "rawScores": {"org": 2.1, "cont": 0.9, "exp": 3.4},
    "model": {"name": "m2-klue-essay", "version": "3.1", "revision": 1},
}


def call(handler: Any, path: str = "m2") -> Any:
    async def run() -> Any:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(base_url="http://scoring", transport=transport) as http:
            client = ScoringClient(http)
            if path == "m2":
                return await client.m2_scores({"text": "x"}, timeout=3.0)
            return await client.m1_check({"problem": "x"}, timeout=3.0)

    return asyncio.run(run())


def test_active_m2_scores_are_parsed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=ESSAY)

    result = call(handler)
    assert result.scores == {"org": 2, "cont": 1, "exp": 3}
    assert result.model.label == "m2-klue-essay@3.1"
    assert seen[0].url.path == "/internal/m2/scores"
    assert seen[0].extensions["timeout"]["read"] == 3.0


@pytest.mark.parametrize("path", ["m2", "m1"])
def test_inactive_is_none(path: str) -> None:
    assert call(lambda _: httpx.Response(200, json={"active": False}), path) is None


@pytest.mark.parametrize(
    ("response", "retryable"),
    [
        (httpx.Response(503, json={"code": "SCORING_UNAVAILABLE"}), True),
        (httpx.Response(400, json={"code": "VALIDATION_FAILED"}), False),
        (httpx.Response(200, text="not json"), False),
        (httpx.Response(200, json={**ESSAY, "scores": {"org": 1}}), False),
        (httpx.Response(200, json={"active": True}), False),
    ],
)
def test_failures_are_not_inactive(response: httpx.Response, retryable: bool) -> None:
    with pytest.raises(ScoringUnavailable) as caught:
        call(lambda _: response)
    assert caught.value.retryable is retryable


def test_transport_error_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ScoringUnavailable) as caught:
        call(handler)
    assert caught.value.retryable is True
