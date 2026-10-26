"""LlmClient 사용량 → llm.usage.recorded 발행 연결 (NFR-PRF-02).

LlmClient의 recorder는 요청마다 호출되는 동기 콜백이라, 발행(UsagePublisher)은
백그라운드 작업으로 넘겨 판정·되묻기 응답을 막지 않음 (아키텍처 1.6 best-effort).
"""

import asyncio
import logging

from app.llm.base import LlmUsage
from app.messaging.publisher import UsagePublisher

logger = logging.getLogger(__name__)


class BackgroundUsageRecorder:
    def __init__(self, publisher: UsagePublisher) -> None:
        self._publisher = publisher
        self._pending: set[asyncio.Task[None]] = set()

    def __call__(self, usage: LlmUsage) -> None:
        task = asyncio.get_running_loop().create_task(self._send(usage))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _send(self, usage: LlmUsage) -> None:
        try:
            await self._publisher.publish(
                usage.call_type,  # type: ignore[arg-type]
                usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=usage.latency_ms,
                success=usage.success,
                prompt_version=usage.prompt_version,
                error_code=usage.error_code,
            )
        except Exception:  # noqa: BLE001 - 발행 실패가 서비스에 번지지 않음
            logger.warning("사용량 이벤트 발행 실패: call_type=%s", usage.call_type, exc_info=True)

    async def close(self, timeout: float = 2.0) -> None:
        """종료 시 보내던 이벤트를 잠깐 기다림."""
        if self._pending:
            await asyncio.wait(self._pending, timeout=timeout)
