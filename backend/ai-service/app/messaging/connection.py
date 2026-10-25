"""RabbitMQ 연결.

브로커 장애 시 프로세스를 종료하지 않고 재연결 시도, 상태는 readiness로 노출 (아키텍처 1.6).
큐·exchange 선언은 definitions.json만 담당, 서비스 코드에서 선언하지 않음.
"""

import asyncio
import contextlib
import logging

import aio_pika
from aio_pika.abc import AbstractRobustConnection

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0


class AmqpConnection:
    def __init__(self, url: str, retry_interval: float = 5.0) -> None:
        self._url = url
        self._retry_interval = retry_interval
        self._connection: AbstractRobustConnection | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._connect_loop())

    async def _connect_loop(self) -> None:
        # 연결 시도 중 태스크를 취소하면 aio-pika 내부 재연결이 남으므로
        # 취소 대신 중지 신호로 종료
        while not self._stop.is_set():
            try:
                self._connection = await aio_pika.connect_robust(self._url, timeout=CONNECT_TIMEOUT)
                return
            except Exception as exc:  # noqa: BLE001 - 연결 실패 원인과 무관하게 재시도
                logger.warning("RabbitMQ 연결 실패, %s초 후 재시도: %s", self._retry_interval, exc)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), self._retry_interval)

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    @property
    def connection(self) -> AbstractRobustConnection:
        if self._connection is None:
            raise RuntimeError("RabbitMQ 미연결")
        return self._connection

    async def close(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
        if self._connection is not None:
            await self._connection.close()
