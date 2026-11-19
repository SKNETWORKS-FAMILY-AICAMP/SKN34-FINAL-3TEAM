"""활성 tox- 모델로 칸별 글을 창 단위 2분류한다 (api-spec 4.3.4).

창 나누기는 학습·평가(`ml/tox/scripts/eval.py` score_texts)와 같아야 임계값이 그대로 맞는다:
토크나이저 truncation·max_length·stride·return_overflowing_tokens, 창별 막을 확률의 최댓값.
"""

import asyncio
import logging
import math
import time

from starlette.concurrency import run_in_threadpool

from app.errors import ApiError
from app.toxicity.metadata import validate_toxicity
from app.toxicity.models import ToxicityActive, ToxicityInactive, ToxicityRequest

logger = logging.getLogger(__name__)

PREFIX = "tox-"
SCOPE = "answer-filter"
BATCH_WINDOWS = 8


class DeadlineExceeded(Exception):
    """처리 마감(기준안 1.3초)을 넘겨 계산을 멈춤."""


def unavailable():
    return ApiError(503, "SCORING_UNAVAILABLE", "표현 분류 처리 실패")


def positive_probability(logits: list[float], positive: int) -> float:
    if len(logits) != 2 or not all(math.isfinite(x) for x in logits):
        raise ValueError("invalid model outputs")
    other = logits[1 - positive]
    return 1.0 / (1.0 + math.exp(other - logits[positive]))


def classify(loaded, texts: list[str], deadline: float) -> tuple[bool, bool]:
    """(flagged, review). 한 창이라도 임계값 이상이면 바로 멈춘다."""
    settings = validate_toxicity(loaded.training_config, loaded.model.config.to_dict())
    review = False
    for text in texts:
        enc = loaded.tokenizer(
            text,
            truncation=True,
            max_length=settings.max_length,
            stride=settings.stride,
            return_overflowing_tokens=True,
            padding=True,
            return_tensors="pt",
        )
        ids, mask = enc["input_ids"], enc["attention_mask"]
        for start in range(0, len(ids), BATCH_WINDOWS):
            if time.monotonic() > deadline:
                raise DeadlineExceeded
            rows = loaded.predict(
                {
                    "input_ids": ids[start : start + BATCH_WINDOWS],
                    "attention_mask": mask[start : start + BATCH_WINDOWS],
                }
            )
            for row in rows:
                prob = positive_probability(row, settings.positive)
                if prob >= settings.threshold:
                    return True, False
                if settings.review_threshold is not None and prob >= settings.review_threshold:
                    review = True
    return False, review


class ToxicityService:
    def __init__(self, registry, *, queue_timeout: float = 1.0, deadline: float = 1.3) -> None:
        self.registry = registry
        # M2 Semaphore(1)과 섞지 않는 tox 전용 게이트
        self._gate = asyncio.Semaphore(1)
        self._queue_timeout = queue_timeout
        self._deadline = deadline

    async def check(self, request: ToxicityRequest):
        try:
            await asyncio.wait_for(self._gate.acquire(), timeout=self._queue_timeout)
        except TimeoutError:
            logger.warning("Toxicity check skipped reason=QUEUE_TIMEOUT")
            raise unavailable() from None
        started = time.monotonic()
        name, result = None, "FAILED"
        try:
            # 대기 후 확인한다. 실행 중 모델이 바뀌어도 응답은 사용한 버전과 일치한다.
            models = self.registry.active_with_prefix(PREFIX, SCOPE)
            if not models:
                result = "INACTIVE"
                return ToxicityInactive()
            if len(models) > 1:
                logger.warning("Toxicity check skipped reason=MULTIPLE_ACTIVE_MODELS")
                raise unavailable()
            loaded = models[0]
            name = f"{loaded.metadata.name}@{loaded.metadata.version}"
            flagged, review = await run_in_threadpool(
                classify, loaded, request.texts, started + self._deadline
            )
            result = "FLAGGED" if flagged else "REVIEW" if review else "PASSED"
            return ToxicityActive(
                flagged=flagged,
                review=review,
                model={
                    "name": loaded.metadata.name,
                    "version": loaded.metadata.version,
                    "revision": loaded.metadata.revision,
                },
            )
        except ApiError:
            raise
        except DeadlineExceeded:
            result = "DEADLINE"
            raise unavailable() from None
        except Exception as exc:
            logger.warning("Toxicity inference failed error_type=%s", type(exc).__name__)
            raise unavailable() from None
        finally:
            self._gate.release()
            # 원문·점수·학생 ID 없이 모델·결과·지연만 남긴다 (NFR-SEC-05)
            logger.info(
                "Toxicity check model=%s result=%s latency_ms=%d",
                name,
                result,
                int((time.monotonic() - started) * 1000),
            )
