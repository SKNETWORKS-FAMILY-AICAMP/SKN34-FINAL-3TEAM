"""승인 범위 검사 → 같은 모델 snapshot으로 CPU 추론 → 보정 점수 반환."""

import asyncio
import logging
import math
import time
from bisect import bisect_right

from starlette.concurrency import run_in_threadpool

from app.errors import ApiError
from app.m2.models import ITEMS, M2Active, M2Inactive, M2Request

logger = logging.getLogger(__name__)


def unavailable():
    return ApiError(503, "SCORING_UNAVAILABLE", "채점 처리 실패")


def flag(value):
    if value is True or value == "True":
        return True
    if value is False or value == "False":
        return False
    raise ValueError("invalid training flag")


def infer(loaded, request: M2Request) -> M2Active:
    config, cuts = loaded.training_config, loaded.score_cuts
    narrative = request.inputType == "NARRATIVE"
    if (
        config.get("head") != "reg"
        or config.get("dataset") != ("descriptive" if narrative else "essay")
        or flag(config.get("with_keyword")) != narrative
        or flag(config.get("with_purpose"))
        or flag(config.get("with_exemplar"))
    ):
        raise ValueError("unsupported training configuration")
    length = int(config["max_length"])
    if not 8 <= length <= 512 or not isinstance(cuts, dict) or set(cuts) != set(ITEMS):
        raise ValueError("invalid scoring metadata")
    for item in ITEMS:
        edges = cuts[item]
        if (
            not isinstance(edges, list)
            or len(edges) != (3 if item == "hol" else 4)
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in edges)
            or any(a >= b for a, b in zip(edges, edges[1:], strict=False))
        ):
            raise ValueError("invalid score cuts")
    first = f"[학년] 초{request.grade} [지시문] {request.prompt}"
    if narrative:
        first += " [핵심어] " + ",".join(request.keywords)
    tokenizer = loaded.tokenizer
    # only_second는 첫 문장을 자르지 않는다. 문항이 너무 길면 추론 장애와 구분한다.
    first_ids = tokenizer(first, add_special_tokens=False)["input_ids"]
    if len(first_ids) + tokenizer.num_special_tokens_to_add(pair=True) >= length:
        raise ApiError(400, "VALIDATION_FAILED", "지시문·핵심어가 모델 입력 한도를 초과했습니다")
    inputs = tokenizer(
        first,
        request.text,
        truncation="only_second",
        max_length=length,
        return_tensors="pt",
    )
    raw = loaded.predict(inputs)
    if len(raw) != 1 or len(raw[0]) != len(ITEMS) or not all(math.isfinite(x) for x in raw[0]):
        raise ValueError("invalid model outputs")
    raw_scores = dict(zip(ITEMS, raw[0], strict=True))
    scores = {item: bisect_right(cuts[item], value) + 1 for item, value in raw_scores.items()}
    return M2Active(
        inputType=request.inputType,
        scores=scores,
        rawScores=raw_scores,
        model={
            "name": loaded.metadata.name,
            "version": loaded.metadata.version,
            "revision": loaded.metadata.revision,
        },
    )


class M2Service:
    def __init__(self, registry, usage, *, queue_timeout=1.0):
        self.registry, self.usage = registry, usage
        self._gate = asyncio.Semaphore(1)
        self._queue_timeout = queue_timeout

    async def score(self, request: M2Request):
        if request.grade not in (5, 6) or (
            request.inputType == "NARRATIVE" and not request.keywords
        ):
            return M2Inactive()
        kind = request.inputType.lower()
        name = "m2-klue-" + ("narrative" if kind == "narrative" else "essay")
        scope = f"judgment/grade-{request.grade}/{kind}"
        try:
            await asyncio.wait_for(self._gate.acquire(), timeout=self._queue_timeout)
        except TimeoutError:
            raise unavailable() from None
        started, loaded, success, error_code = time.perf_counter(), None, False, None
        try:
            # 대기 후 scope를 재확인한다. 실행 중 모델이 바뀌어도 응답은 사용한 버전과 일치한다.
            loaded = self.registry.get(name, scope)
            if loaded is None:
                return M2Inactive()
            result = await run_in_threadpool(infer, loaded, request)
            success = True
            return result
        except ApiError as exc:
            error_code = exc.code
            raise
        except Exception as exc:
            error_code = "SCORING_UNAVAILABLE"
            logger.warning("M2 inference failed error_type=%s", type(exc).__name__)
            raise unavailable() from None
        finally:
            self._gate.release()
            if loaded is not None:
                self.usage.submit(
                    "M2",
                    f"{loaded.metadata.name}@{loaded.metadata.version}",
                    input_tokens=None,
                    output_tokens=None,
                    latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    success=success,
                    error_code=error_code,
                )
