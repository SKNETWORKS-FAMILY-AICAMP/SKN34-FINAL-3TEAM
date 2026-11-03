"""승인 범위 검사 → 같은 모델 snapshot으로 CPU 추론 → 보정 점수 반환."""

import asyncio
import logging
import math
import time
from bisect import bisect_right

from starlette.concurrency import run_in_threadpool

from app.errors import ApiError
from app.m2.content3_rule import content3_score
from app.m2.metadata import validate_metadata
from app.m2.models import M2Active, M2Inactive, M2Request

logger = logging.getLogger(__name__)


def unavailable():
    return ApiError(503, "SCORING_UNAVAILABLE", "채점 처리 실패")


def infer(loaded, request: M2Request, *, content3_rule_enabled: bool = False) -> M2Active:
    config, cuts = loaded.training_config, loaded.score_cuts
    narrative = request.inputType == "NARRATIVE"
    items, width, no_prompt, length = validate_metadata(loaded.metadata.name, config, cuts)
    if narrative != (loaded.metadata.name == "m2-klue-narrative"):
        raise ValueError("model and request type mismatch")
    first = f"[학년] 초{request.grade}"
    if not no_prompt:
        first += f" [지시문] {request.prompt}"
    if narrative:
        first += " [핵심어] " + (", " if no_prompt else ",").join(request.keywords)
    elif no_prompt:
        first += f" [글 종류] {request.essayType}"
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
    if len(raw) != 1 or len(raw[0]) != width or not all(math.isfinite(x) for x in raw[0]):
        raise ValueError("invalid model outputs")
    raw_scores = dict(zip(items, raw[0][: len(items)], strict=True))
    scores = {
        item: bisect_right(cuts[item], value) + (0 if width == 14 else 1)
        for item, value in raw_scores.items()
    }
    if (
        content3_rule_enabled
        and narrative
        and request.grade in (5, 6)
        and loaded.metadata.name == "m2-klue-narrative"
        and loaded.metadata.version == "3.0"
    ):
        raw_scores["content_3"], scores["content_3"] = content3_score(
            raw_scores["content_3"], request.text, request.keywords
        )
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
    def __init__(self, registry, usage, *, queue_timeout=1.0, content3_rule_enabled: bool = False):
        self.registry, self.usage = registry, usage
        self._gate = asyncio.Semaphore(1)
        self._queue_timeout = queue_timeout
        self._content3_rule_enabled = content3_rule_enabled

    async def score(self, request: M2Request):
        if request.grade not in ((5, 6) if request.inputType == "NARRATIVE" else (4, 5, 6)) or (
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
            if request.grade == 4 and loaded.training_config.get("dataset") != "essay545":
                loaded = None  # 비활성 경로는 추론하지 않아 사용량도 발행하지 않는다.
                return M2Inactive()
            result = await run_in_threadpool(
                infer, loaded, request, content3_rule_enabled=self._content3_rule_enabled
            )
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
