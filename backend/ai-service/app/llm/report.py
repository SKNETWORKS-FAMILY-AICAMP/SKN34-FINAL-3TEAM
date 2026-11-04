"""주간 리포트 전용 RunPod Gemma 연결. 전역 LLM 설정과 분리한다."""

import asyncio
import json
import logging
import re
from typing import Annotated, Any

import httpx
from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.llm.base import (
    LlmClient,
    LlmError,
    LlmRequest,
    ProviderResponse,
    T,
    UnconfiguredLlm,
    UsageRecorder,
    status_error,
)
from app.llm.providers import _validate, get_llm, strict_schema

logger = logging.getLogger(__name__)


class RunPodReportLlm(LlmClient):
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        recorder: UsageRecorder,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        model: str = "gemma-4-26b-a4b-it-qat-awq-int4",
        timeout: float = 120,
    ) -> None:
        match = re.fullmatch(
            r"https://api\.runpod\.ai/v2/([a-zA-Z0-9_-]+)(?:/(?:run|runsync))?/?", endpoint
        )
        if not match:
            raise ValueError("Gemma endpoint must be an HTTPS RunPod v2 endpoint")
        # 재접수로 중복 추론이 발생하지 않게 요청 재시도는 하지 않는다.
        super().__init__(model, 0, recorder, 0, timeout)
        self._base = f"https://api.runpod.ai/v2/{match.group(1)}"
        self._key = api_key
        self._transport = transport

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        job_id: str | None = None
        terminal = False
        async with httpx.AsyncClient(
            base_url=self._base + "/",
            transport=self._transport,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {self._key}"},
            timeout=10,
        ) as client:
            try:
                async with asyncio.timeout(request.timeout):
                    schema = strict_schema(request.output)
                    payload = {
                        "input": {
                            "openai_route": "/v1/chat/completions",
                            "openai_input": {
                                "model": self.model,
                                "messages": [
                                    {
                                        "role": "system",
                                        "content": request.system
                                        + "\n아래 스키마를 따르는 JSON 객체 하나만 출력하세요."
                                        + " 설명이나 코드 블록은 쓰지 마세요.\n"
                                        + json.dumps(schema, ensure_ascii=False),
                                    },
                                    {"role": "user", "content": request.user},
                                ],
                                "max_tokens": request.max_tokens,
                                "temperature": 0,
                                "stream": False,
                                "response_format": {
                                    "type": "json_schema",
                                    "json_schema": {
                                        "name": request.output.__name__,
                                        "schema": schema,
                                        "strict": True,
                                    },
                                },
                            },
                        },
                        "policy": {
                            "executionTimeout": max(1000, int(request.timeout * 1000)),
                            "ttl": max(60000, int(request.timeout * 2000)),
                        },
                    }
                    response = await client.post("run", json=payload)
                    self._check_status(response)
                    result = response.json()
                    job_id = result.get("id")
                    if not isinstance(job_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", job_id):
                        job_id = None
                        raise LlmError("LLM_INVALID_OUTPUT", retryable=False)
                    while result.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
                        await asyncio.sleep(0.5)
                        response = await client.get(f"status/{job_id}")
                        self._check_status(response)
                        result = response.json()
                    terminal = result.get("status") in (
                        "COMPLETED",
                        "FAILED",
                        "CANCELLED",
                        "TIMED_OUT",
                    )
                    if result.get("status") != "COMPLETED":
                        raise LlmError("LLM_SERVER_ERROR", retryable=True)
                    return self._decode(request, result.get("output"))
            except (TimeoutError, httpx.TimeoutException) as exc:
                raise LlmError("LLM_TIMEOUT", retryable=True) from exc
            except httpx.RequestError as exc:
                raise LlmError("LLM_CONNECTION", retryable=True) from exc
            except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
                raise LlmError("LLM_INVALID_OUTPUT", retryable=True) from exc
            finally:
                if job_id and not terminal:
                    try:
                        # 외부 요청 취소 시에도 접수된 작업 정리를 시도한다.
                        await asyncio.wait_for(
                            asyncio.shield(client.post(f"cancel/{job_id}", timeout=2)), 2
                        )
                    except Exception:
                        logger.warning("리포트 Gemma 작업 취소 실패; 원문·자격증명은 생략")

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if not response.is_success:
            raise status_error(response.status_code)

    def _decode(self, request: LlmRequest[T], output: Any) -> ProviderResponse[T]:
        if isinstance(output, list) and len(output) == 1:
            output = output[0]
        if not isinstance(output, dict):
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True)
        model = output.get("model") or self.model
        usage = output.get("usage") or {}
        tokens = {
            "model": model,
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        }
        choices = output.get("choices") or []
        choice = choices[0] if choices else {}
        if choice.get("finish_reason") == "length":
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True, **tokens)
        message = choice.get("message") or {}
        if message.get("refusal") or choice.get("finish_reason") == "content_filter":
            raise LlmError("LLM_REFUSED", retryable=False, **tokens)
        text = message.get("content") or choice.get("text")
        if not text and isinstance(choice.get("tokens"), list):
            text = "".join(choice["tokens"])
        if not isinstance(text, str) or not text.strip():
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True, **tokens)
        return ProviderResponse(_validate(request, text, tokens), **tokens)


def create_report_llm(settings: Settings, default: LlmClient, recorder: UsageRecorder) -> LlmClient:
    if settings.report_llm_provider == "default":
        return default
    endpoint = settings.sagomungchi_sllm_serverless_gemma
    key = settings.sagomungchi_sllm_serverless_key_gemma
    if not endpoint or not key:
        return UnconfiguredLlm("gemma-serverless", recorder)
    return RunPodReportLlm(
        endpoint,
        key,
        recorder,
        model=settings.report_gemma_model,
        timeout=settings.report_gemma_timeout,
    )


def get_report_llm(request: Request, default: Annotated[LlmClient, Depends(get_llm)]) -> LlmClient:
    if get_settings().report_llm_provider == "default":
        return default
    return getattr(request.app.state, "report_llm", default)
