import asyncio
import io
import json
import time

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError
from pydantic import BaseModel

from app.config import Settings
from app.llm.base import LlmUnavailable, UnconfiguredLlm
from app.llm.report import SageMakerReportLlm, create_report_llm

ENDPOINT = "synthetic-endpoint"
COMPONENT = "synthetic-endpoint-explain"


class Output(BaseModel):
    narrative: str


class FakeRuntime:
    """boto3 sagemaker-runtime 대역. 호출 인자를 기록하고 정해 둔 결과를 돌려준다."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def invoke_endpoint(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        if callable(self.result):
            return self.result(kwargs)
        return {"Body": io.BytesIO(json.dumps(self.result).encode())}


def completion(content, finish="stop"):
    return {
        "model": COMPONENT,
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 25},
    }


def client_error(code, message="synthetic", status=400, **extra):
    return ClientError(
        {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
            **extra,
        },
        "InvokeEndpoint",
    )


def make(result, usage=None, timeout=70):
    runtime = FakeRuntime(result)
    llm = SageMakerReportLlm(
        ENDPOINT,
        COMPONENT,
        (usage if usage is not None else []).append,
        region="ap-northeast-2",
        model="report-gemma",
        timeout=timeout,
        client=runtime,
    )
    return llm, runtime


def generate(llm, max_tokens=1024):
    return asyncio.run(
        llm.generate(
            system="Use the supplied records",
            user="synthetic record",
            output=Output,
            call_type="REPORT_NARRATIVE",
            prompt_version="report@1",
            max_tokens=max_tokens,
        )
    )


def test_reports_fail_closed_without_sagemaker_settings_even_with_general_llm_configured():
    settings = Settings(
        internal_token="test", openai_api_key="general-api-key", openai_model="other-model"
    )
    assert isinstance(create_report_llm(settings, lambda _: None), UnconfiguredLlm)
    only_endpoint = Settings(internal_token="test", report_llm_endpoint=ENDPOINT)
    assert isinstance(create_report_llm(only_endpoint, lambda _: None), UnconfiguredLlm)


def test_summary_and_detail_factories_use_the_same_lora_component(monkeypatch, tmp_path):
    from app.llm.providers import create_explanation_llm

    # 개발 PC의 AWS 프로필을 읽지 않게 가상 자격 증명만 둔다.
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic")
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    settings = Settings(
        internal_token="test",
        report_llm_endpoint=ENDPOINT,
        report_llm_component=COMPONENT,
        report_llm_endpoint_url="http://llm-stub:8080",
    )
    for llm in (
        create_report_llm(settings, lambda _: None),
        create_explanation_llm(settings, lambda _: None),
    ):
        assert isinstance(llm, SageMakerReportLlm)
        assert llm.model == settings.report_gemma_model
        assert llm._component == COMPONENT
        assert llm._client.meta.endpoint_url == "http://llm-stub:8080"
        assert llm._client.meta.region_name == "ap-northeast-2"
        assert llm._client.meta.config.read_timeout == 70
        assert llm._client.meta.config.retries["total_max_attempts"] == 1


def test_one_synchronous_call_selects_the_lora_component_and_maps_usage():
    usage = []
    llm, runtime = make(completion('{"narrative":"가상 기록 요약입니다."}'), usage)
    result = generate(llm, max_tokens=1536)
    assert result.data.narrative == "가상 기록 요약입니다."
    # 응답 model(IC 이름) 대신 설정한 모델 이름을 남긴다.
    assert result.model == "report-gemma"
    assert usage[0].call_type == "REPORT_NARRATIVE"
    assert usage[0].output_tokens == 25
    assert usage[0].success
    [call] = runtime.calls
    assert call["EndpointName"] == ENDPOINT
    assert call["InferenceComponentName"] == COMPONENT
    assert call["ContentType"] == "application/json"
    body = json.loads(call["Body"])
    assert body["messages"][1]["content"] == "synthetic record"
    assert "narrative" in body["messages"][0]["content"]
    assert body["max_tokens"] == 1536
    assert body["stream"] is False
    assert body["response_format"]["json_schema"]["name"] == "Output"


def test_no_capacity_outside_the_window_fails_once_without_fallback_or_retry():
    usage = []
    error = client_error(
        "ValidationError",
        "Inference Component has no capacity to process this request. synthetic record",
    )
    llm, runtime = make(error, usage)
    with pytest.raises(LlmUnavailable) as raised:
        generate(llm)
    assert raised.value.code == "LLM_NO_CAPACITY"
    assert raised.value.retryable is False
    assert "synthetic record" not in str(raised.value)
    assert len(runtime.calls) == 1
    assert usage[0].error_code == "LLM_NO_CAPACITY"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (client_error("ModelError", status=424, OriginalStatusCode=500), "LLM_SERVER_ERROR"),
        (client_error("ModelError", status=424, OriginalStatusCode=400), "LLM_BAD_REQUEST"),
        (client_error("ThrottlingException", status=429), "LLM_RATE_LIMITED"),
        (client_error("AccessDeniedException", status=403), "LLM_AUTH_FAILED"),
        (client_error("ValidationError", "Endpoint not found", status=400), "LLM_BAD_REQUEST"),
        (client_error("ServiceUnavailable", status=503), "LLM_SERVER_ERROR"),
        (ReadTimeoutError(endpoint_url="https://runtime.sagemaker"), "LLM_TIMEOUT"),
        (EndpointConnectionError(endpoint_url="https://runtime.sagemaker"), "LLM_CONNECTION"),
    ],
)
def test_failures_are_classified_without_reposting(error, code):
    llm, runtime = make(error)
    with pytest.raises(LlmUnavailable) as raised:
        generate(llm)
    assert raised.value.code == code
    assert len(runtime.calls) == 1


def test_deadline_shorter_than_the_call_times_out():
    def slow(_):
        time.sleep(0.3)
        return {"Body": io.BytesIO(b"{}")}

    llm, _ = make(slow, timeout=0.05)
    with pytest.raises(LlmUnavailable) as raised:
        generate(llm)
    assert raised.value.code == "LLM_TIMEOUT"


@pytest.mark.parametrize(
    "reply",
    [
        # 인용 부호를 이스케이프하지 않아 공백을 max_tokens까지 반복한 경우(infra.md 9.13.9)
        completion('{"narrative": "처음에는 "\t\t\t\t\t\t', finish="length"),
        completion("not JSON"),
        completion(""),
        {"choices": []},
        ["not", "an", "object"],
    ],
)
def test_invalid_or_truncated_output_remains_failure_instead_of_becoming_a_report(reply):
    llm, _ = make(reply)
    with pytest.raises(LlmUnavailable) as raised:
        generate(llm)
    assert raised.value.code == "LLM_INVALID_OUTPUT"


def test_refusal_is_not_retried():
    reply = {"choices": [{"message": {"content": None, "refusal": "no"}, "finish_reason": "stop"}]}
    llm, runtime = make(reply)
    with pytest.raises(LlmUnavailable) as raised:
        generate(llm)
    assert raised.value.code == "LLM_REFUSED"
    assert len(runtime.calls) == 1


@pytest.mark.parametrize("penalty", [None, 1.1])
def test_repetition_penalty_is_sent_only_when_requested(penalty):
    llm, runtime = make(completion('{"narrative":"가상 기록 요약입니다."}'))
    asyncio.run(
        llm.generate(
            system="Use the supplied records",
            user="synthetic record",
            output=Output,
            call_type="REPORT_EXPLANATION",
            prompt_version="report-explanation@4",
            repetition_penalty=penalty,
        )
    )
    body = json.loads(runtime.calls[0]["Body"])
    assert body.get("repetition_penalty") == penalty
    assert ("repetition_penalty" in body) is (penalty is not None)
