import asyncio
import json

import httpx
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm.base import LlmUnavailable, UnconfiguredLlm
from app.llm.report import RunPodReportLlm, create_report_llm


class Output(BaseModel):
    narrative: str


def generate(llm):
    return asyncio.run(
        llm.generate(
            system="Use the supplied records",
            user="synthetic record",
            output=Output,
            call_type="REPORT_NARRATIVE",
            prompt_version="report@1",
        )
    )


def test_scoped_provider_preserves_default_and_fails_closed_without_gemma_key():
    default = UnconfiguredLlm("existing-model", lambda _: None)
    assert create_report_llm(Settings(internal_token="test"), default, lambda _: None) is default
    configured = create_report_llm(
        Settings(internal_token="test", report_llm_provider="runpod_gemma"), default, lambda _: None
    )
    assert configured is not default
    assert isinstance(configured, UnconfiguredLlm)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com/run",
        "http://api.runpod.ai/v2/demo/run",
        "https://api.runpod.ai/v2/demo/run?key=secret",
        "https://api.runpod.ai.evil.test/v2/demo/run",
    ],
)
def test_rejects_endpoint_that_could_leak_the_key(endpoint):
    with pytest.raises(ValueError):
        RunPodReportLlm(endpoint, "test-key", lambda _: None)


@pytest.mark.parametrize("legacy", [False, True])
def test_async_job_maps_output_model_and_usage_to_existing_report_contract(legacy):
    calls, usage = [], []

    def handler(request):
        calls.append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer test-key"
        if request.url.path.endswith("/run"):
            body = json.loads(request.content)
            assert body["input"]["openai_input"]["messages"][1]["content"] == "synthetic record"
            assert "narrative" in body["input"]["openai_input"]["messages"][0]["content"]
            assert body["input"]["openai_input"]["stream"] is False
            return httpx.Response(200, json={"id": "job-1", "status": "IN_QUEUE"})
        text = '{"narrative":"가상 기록 요약입니다."}'
        choice = {"tokens": [text]} if legacy else {"message": {"content": text}}
        output = {
            "model": "test-gemma-model",
            "choices": [choice],
            "usage": {"prompt_tokens": 120, "completion_tokens": 25},
        }
        return httpx.Response(
            200,
            json={"id": "job-1", "status": "COMPLETED", "output": [output] if legacy else output},
        )

    llm = RunPodReportLlm(
        "https://api.runpod.ai/v2/demo/runsync",
        "test-key",
        usage.append,
        httpx.MockTransport(handler),
    )
    result = generate(llm)
    assert result.data.narrative == "가상 기록 요약입니다."
    assert result.model == "test-gemma-model"
    assert usage[0].call_type == "REPORT_NARRATIVE"
    assert usage[0].output_tokens == 25
    assert calls == [("POST", "/v2/demo/run"), ("GET", "/v2/demo/status/job-1")]


def test_timeout_cancels_accepted_job_without_duplicate_submission():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"id": "job-1", "status": "IN_QUEUE"})

    llm = RunPodReportLlm(
        "https://api.runpod.ai/v2/demo/run",
        "test-key",
        lambda _: None,
        httpx.MockTransport(handler),
    )
    llm._timeout = 0.02
    with pytest.raises(LlmUnavailable) as error:
        generate(llm)
    assert error.value.code == "LLM_TIMEOUT"
    assert calls == ["/v2/demo/run", "/v2/demo/cancel/job-1"]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_failure_is_sanitized_and_never_falls_back_or_reposts(status):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(status, text="test-key synthetic record sensitive response")

    llm = RunPodReportLlm(
        "https://api.runpod.ai/v2/demo/run",
        "test-key",
        lambda _: None,
        httpx.MockTransport(handler),
    )
    with pytest.raises(LlmUnavailable) as error:
        generate(llm)
    assert "test-key" not in str(error.value)
    assert calls == ["/v2/demo/run"]


def test_invalid_completed_output_remains_failure_instead_of_becoming_a_report():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "id": "job-1",
                "status": "COMPLETED",
                "output": {"choices": [{"text": "not JSON"}]},
            },
        )

    llm = RunPodReportLlm(
        "https://api.runpod.ai/v2/demo/run",
        "test-key",
        lambda _: None,
        httpx.MockTransport(handler),
    )
    with pytest.raises(LlmUnavailable) as error:
        generate(llm)
    assert error.value.code == "LLM_INVALID_OUTPUT"
