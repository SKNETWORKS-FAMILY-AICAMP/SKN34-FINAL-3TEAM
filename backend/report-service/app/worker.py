"""report-worker 진입점: report.generate·student.deleted 소비.

소비자는 generation/consumer.py·deletion/consumer.py에서 작성 후
messaging/consumer.py의 EventConsumer.consume(큐, 핸들러)로 여기서 시작.
"""

import asyncio
import contextlib
import logging
import signal

from app.config import get_settings
from app.messaging.connection import AmqpConnection


async def run() -> None:
    amqp = AmqpConnection(get_settings().rabbitmq_url)
    amqp.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows 로컬 실행
            loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    await amqp.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
