"""Pod별 모델 버전 구독. 재연결마다 큐를 먼저 바인딩하고 snapshot으로 복구한다."""

import asyncio
import contextlib
import logging
from typing import Literal
from uuid import UUID

from aio_pika.abc import AbstractIncomingMessage
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.messaging.connection import AmqpConnection
from app.messaging.envelope import EventEnvelope
from app.model_sync import ModelSync
from app.model_versions import Scope

logger = logging.getLogger(__name__)


class ActivationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    kind: Literal["MODEL", "PROMPT", "RUBRIC", "GENERATION"]
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    refId: UUID | None
    artifactUri: str | None
    scopes: tuple[Scope, ...] = Field(min_length=1, max_length=100)
    revision: int = Field(strict=True, ge=1)
    activatedAt: AwareDatetime
    previousVersionId: UUID | None

    @field_validator("scopes")
    @classmethod
    def unique_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate scopes")
        return value


class ActivationEnvelope(EventEnvelope[ActivationData]):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(...)
    specversion: Literal["1.0"] = Field(...)
    type: Literal["model.version.activated"]
    time: AwareDatetime = Field(...)
    dataschema: Literal["model.version.activated.v1"]

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        UUID(value)
        return value


class ModelVersionConsumer:
    def __init__(self, amqp: AmqpConnection, sync: ModelSync, retry_interval: float) -> None:
        self._amqp = amqp
        self._sync = sync
        self._retry_interval = retry_interval
        self._task: asyncio.Task[None] | None = None
        self._bound = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def is_ready(self) -> bool:
        return self._bound and self._amqp.is_connected and await self._sync.is_ready()

    async def _run(self) -> None:
        while True:
            try:
                if self._amqp.is_connected:
                    await self._session()
            except Exception as exc:
                logger.warning("Model subscription retry error_type=%s", type(exc).__name__)
            await asyncio.sleep(self._retry_interval)

    async def _session(self) -> None:
        connection = self._amqp.connection
        disconnected = asyncio.Event()

        def on_close(*_args, **_kwargs):
            self._bound = False
            disconnected.set()

        connection.close_callbacks.add(on_close)
        channel = None
        self._sync.reset()
        try:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=100)
            exchange = await channel.get_exchange("events.topic", ensure=True)
            # 자동 복구에 맡기지 않고 재연결 시 새 큐 + snapshot 순서를 다시 실행한다.
            queue = await channel.declare_queue("", exclusive=True, auto_delete=True, robust=False)
            await queue.bind(exchange, routing_key="model.version.*", robust=False)
            await queue.consume(self.receive, robust=False)
            if disconnected.is_set():
                return
            self._bound = True
            logger.info("Model subscription bound queue=%s", queue.name)
            self._sync.start()
            await disconnected.wait()
        finally:
            self._bound = False
            await self._sync.stop()
            connection.close_callbacks.discard(on_close)
            if channel is not None:
                with contextlib.suppress(Exception):
                    await channel.close()

    async def receive(self, message: AbstractIncomingMessage) -> None:
        try:
            envelope = ActivationEnvelope.model_validate_json(message.body)
            self._sync.offer(envelope.data.model_dump(mode="json"))
        except (ValueError, TypeError):
            # 원문·URI·검증 예외 본문은 로그에 넣지 않는다. 잘못된 메시지는 재시도 없음.
            logger.warning("Invalid model activation event ignored")
        await message.ack()

    async def close(self) -> None:
        self._bound = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
