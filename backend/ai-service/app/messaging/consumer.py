"""Pod별 활성 버전 구독. 바인딩 후 core snapshot으로 초기화·재연결 복구."""

import asyncio
import contextlib
import json
import logging
from uuid import UUID

from aio_pika.abc import AbstractIncomingMessage
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import AwareDatetime, ConfigDict, Field, field_validator

from app import tracing
from app.messaging.connection import AmqpConnection
from app.messaging.envelope import EventEnvelope
from app.prompt_versions.models import ActiveVersionItem
from app.prompt_versions.service import PromptSync

logger = logging.getLogger(__name__)


class ActivationData(ActiveVersionItem):
    previous_version_id: UUID | None = Field(alias="previousVersionId")


class ActivationEnvelope(EventEnvelope[ActivationData]):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(...)
    specversion: str = Field(pattern=r"^1\.0$")
    type: str = Field(pattern=r"^model\.version\.activated$")
    time: AwareDatetime = Field(...)
    dataschema: str = Field(pattern=r"^model\.version\.activated\.v1$")

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        UUID(value)
        return value


class ModelVersionConsumer:
    def __init__(
        self,
        amqp: AmqpConnection,
        sync: PromptSync,
        retry_interval: float = 5.0,
    ) -> None:
        self._amqp = amqp
        self._sync = sync
        self._retry_interval = retry_interval
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._bound = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def is_ready(self) -> bool:
        return self._bound and self._amqp.is_connected and self._sync.is_ready()

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self._amqp.is_connected:
                    await self._session()
            except Exception as exc:
                logger.warning("Prompt subscription retry error_type=%s", type(exc).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), self._retry_interval)

    async def _session(self) -> None:
        connection = self._amqp.connection
        disconnected = asyncio.Event()

        def on_close(*_args: object, **_kwargs: object) -> None:
            self._bound = False
            self._sync.reset()
            disconnected.set()

        connection.close_callbacks.add(on_close)
        channel = None
        self._sync.reset()
        try:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=100)
            exchange = await channel.get_exchange("events.topic", ensure=True)
            queue = await channel.declare_queue("", exclusive=True, auto_delete=True, robust=False)
            await queue.bind(exchange, routing_key="model.version.*", robust=False)
            await queue.consume(self.receive, robust=False)
            if disconnected.is_set():
                return
            self._bound = True
            logger.info("Prompt subscription bound queue=%s", queue.name)
            await self._sync.synchronize(disconnected)
            await disconnected.wait()
        finally:
            self._bound = False
            self._sync.reset()
            connection.close_callbacks.discard(on_close)
            if channel is not None:
                with contextlib.suppress(Exception):
                    await channel.close()

    async def receive(self, message: AbstractIncomingMessage) -> None:
        # 봉투 traceparent를 부모로 소비 span (아키텍처 4.6). 속성은 이벤트 종류·결과만
        with tracing.tracer().start_as_current_span(
            "model.version.activated process",
            context=tracing.parent_context(_traceparent(message.body)),
            kind=SpanKind.CONSUMER,
            attributes={
                "messaging.system": "rabbitmq",
                "messaging.operation.type": "process",
                "messaging.destination.name": "events.topic",
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                envelope = ActivationEnvelope.model_validate_json(message.body)
                item = ActiveVersionItem.model_validate(
                    envelope.data.model_dump(by_alias=True, exclude={"previous_version_id"})
                )
                self._sync.offer(item)
            except (ValueError, TypeError):
                # 학생 원문·URI·파싱 예외 본문은 로그에 넣지 않는다. 형식 오류는 ACK 후 종료.
                logger.warning("Invalid prompt activation event ignored")
                span.set_attribute("error.type", "INVALID_EVENT")
                span.set_status(StatusCode.ERROR)
            await message.ack()

    async def close(self) -> None:
        self._bound = False
        self._sync.reset()
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task


def _traceparent(body: bytes) -> str | None:
    """형식 검증 전 봉투에서 traceparent만 읽음. 형식이 틀려도 소비 span은 이어 준다."""
    try:
        value = json.loads(body).get("traceparent")
    except (ValueError, TypeError, AttributeError):
        return None
    return value if isinstance(value, str) else None
