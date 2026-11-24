"""주간 리포트 전용 Gemma 연결(SageMaker 실시간 엔드포인트, #747). 전역 LLM 설정과 분리한다.

- boto3 `sagemaker-runtime` `invoke_endpoint`(SigV4) 동기 호출 1회. 재접수·재시도는 하지 않는다
- LoRA는 요청 본문의 `model`이 아니라 `InferenceComponentName`(어댑터 IC)으로 붙는다(#746)
- SageMaker 실시간 호출은 60초에 끊긴다. 읽기 타임아웃은 그보다 조금 긴 값(기본 70초)
- 가동 창 밖(IC 사본 0)이면 바로 ValidationError("no capacity")가 온다. 다른 모델로 대체하지
  않고 실패로 돌려 report가 설명 없이 발행한다(#733)
- local·kind·E2E는 `endpoint_url`을 llm-stub으로 바꿔 같은 경로를 탄다
"""

import asyncio
import json
import logging
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    ReadTimeoutError,
)
from fastapi import Request

from app.config import Settings
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
from app.llm.providers import _validate, strict_schema

logger = logging.getLogger(__name__)

# 사본 0일 때의 ValidationError 문구(#746 실측: "Inference Component has no capacity ...")
NO_CAPACITY = "no capacity"


class SageMakerReportLlm(LlmClient):
    def __init__(
        self,
        endpoint: str,
        component: str,
        recorder: UsageRecorder,
        *,
        region: str,
        model: str,
        timeout: float = 70,
        endpoint_url: str | None = None,
        client: Any = None,
    ) -> None:
        # 재접수로 중복 추론이 생기지 않게 요청 재시도는 하지 않는다.
        super().__init__(model, 0, recorder, 0, timeout)
        self._endpoint = endpoint
        self._component = component
        self._client = client or boto3.client(
            "sagemaker-runtime",
            region_name=region,
            endpoint_url=endpoint_url or None,
            config=Config(
                connect_timeout=5,
                read_timeout=timeout,
                retries={"total_max_attempts": 1},
            ),
        )

    async def _request(self, request: LlmRequest[T]) -> ProviderResponse[T]:
        schema = strict_schema(request.output)
        body = {
            # vLLM 응답 이름용. LoRA 선택은 InferenceComponentName이 한다.
            "model": self._component,
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
        }
        if request.repetition_penalty is not None:
            # vLLM 확장 파라미터. 리포트 상세 설명 재생성에서만 켬
            body["repetition_penalty"] = request.repetition_penalty
        try:
            async with asyncio.timeout(request.timeout):
                raw = await asyncio.to_thread(self._invoke, json.dumps(body, ensure_ascii=False))
        except (TimeoutError, ReadTimeoutError, ConnectTimeoutError) as exc:
            raise LlmError("LLM_TIMEOUT", retryable=True) from exc
        except EndpointConnectionError as exc:
            raise LlmError("LLM_CONNECTION", retryable=True) from exc
        except NoCredentialsError as exc:
            raise LlmError("LLM_AUTH_FAILED", retryable=False, sent=False) from exc
        except ClientError as exc:
            raise self._client_error(exc) from exc
        except BotoCoreError as exc:
            raise LlmError("LLM_CONNECTION", retryable=True) from exc
        try:
            return self._decode(request, json.loads(raw))
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True) from exc

    def _invoke(self, body: str) -> bytes:
        response = self._client.invoke_endpoint(
            EndpointName=self._endpoint,
            InferenceComponentName=self._component,
            ContentType="application/json",
            Accept="application/json",
            Body=body.encode("utf-8"),
        )
        return response["Body"].read()

    @staticmethod
    def _client_error(exc: ClientError) -> LlmError:
        """응답 본문·메시지 원문은 남기지 않고 코드로만 분류한다."""
        error = exc.response.get("Error", {})
        code = error.get("Code", "")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 500
        if code == "ValidationError" and NO_CAPACITY in str(error.get("Message", "")).lower():
            # 가동 창 밖. 같은 요청을 다시 보내도 창이 열리기 전에는 실패한다.
            logger.warning("리포트 Gemma 엔드포인트 사본 0(가동 창 밖)")
            return LlmError("LLM_NO_CAPACITY", retryable=False)
        if code == "ModelError":
            # 컨테이너(vLLM)가 돌려준 상태 코드
            return status_error(int(exc.response.get("OriginalStatusCode") or 500))
        if code in ("ThrottlingException", "ModelNotReadyException"):
            return LlmError("LLM_RATE_LIMITED", retryable=True)
        if code in ("AccessDeniedException", "UnrecognizedClientException"):
            return LlmError("LLM_AUTH_FAILED", retryable=False)
        return status_error(int(status))

    def _decode(self, request: LlmRequest[T], output: Any) -> ProviderResponse[T]:
        if not isinstance(output, dict):
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True)
        usage = output.get("usage") or {}
        # 응답 model은 IC 이름이라 사용량·버전에는 설정한 모델 이름을 쓴다(별도 청구 목록과 같음).
        tokens = {
            "model": self.model,
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        }
        choices = output.get("choices") or []
        choice = choices[0] if choices else {}
        if choice.get("finish_reason") == "length":
            # 인용 부호를 이스케이프하지 않아 공백을 반복한 경우 등(infra.md 9.13.9). 설명은 빠진다.
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True, **tokens)
        message = choice.get("message") or {}
        if message.get("refusal") or choice.get("finish_reason") == "content_filter":
            raise LlmError("LLM_REFUSED", retryable=False, **tokens)
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise LlmError("LLM_INVALID_OUTPUT", retryable=True, **tokens)
        return ProviderResponse(_validate(request, text, tokens), **tokens)


def create_report_llm(settings: Settings, recorder: UsageRecorder) -> LlmClient:
    """Reports are pinned to the LoRA inference component; never use the general LLM."""
    if not settings.report_llm_endpoint or not settings.report_llm_component:
        return UnconfiguredLlm(settings.report_gemma_model, recorder)
    return SageMakerReportLlm(
        settings.report_llm_endpoint,
        settings.report_llm_component,
        recorder,
        region=settings.report_llm_region,
        model=settings.report_gemma_model,
        timeout=settings.report_llm_timeout,
        endpoint_url=settings.report_llm_endpoint_url,
    )


def get_report_llm(request: Request) -> LlmClient:
    return request.app.state.report_llm
