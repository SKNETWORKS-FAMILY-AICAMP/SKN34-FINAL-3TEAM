"""답변 표현 분류(tox-) 학습 산출물 검사. 로더와 사전 검사(#368)가 같은 기준 (api-spec 5.2)."""

import math
from dataclasses import dataclass

# int8은 Linear 채널별 동적 양자화만(ml/tox quant.py와 같음, 11/17 서비스 조건 평가로 고름)
QUANTIZATIONS = ("none", "int8-dynamic-channel")


class ClassifierShapeError(ValueError):
    """config.json이 2분류(single_label_classification)가 아님."""


@dataclass(frozen=True)
class ToxicitySettings:
    threshold: float
    review_threshold: float | None
    max_length: int
    stride: int
    positive: int
    int8: bool


def _probability(value) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < 1:
        raise ValueError("invalid threshold")
    return float(value)


def validate_toxicity(training: dict, config: dict) -> ToxicitySettings:
    """`train_info.json`과 `config.json`이 2분류·임계값 계약을 지키는지 확인한다."""
    if not isinstance(training, dict) or not isinstance(config, dict):
        raise ValueError("invalid toxicity metadata")
    threshold = _probability(training.get("threshold"))
    review = training.get("review_threshold")
    if review is not None:
        review = _probability(review)
        if review >= threshold:
            raise ValueError("review_threshold must be below threshold")
    length, stride = training.get("max_length"), training.get("stride")
    if type(length) is not int or type(stride) is not int or not 8 <= length <= 512:
        raise ValueError("invalid window")
    if not 0 <= stride < length - 2:
        raise ValueError("invalid window")
    positive = training.get("positiveLabel", 1)
    if type(positive) is not int or positive not in (0, 1):
        raise ValueError("invalid positive label")
    quantization = training.get("quantization", "none")
    if quantization not in QUANTIZATIONS:
        raise ValueError("unsupported quantization")
    labels, width = config.get("id2label"), config.get("num_labels")
    two_labels = (
        # config.json은 문자열 키, 불러온 HF config.to_dict()는 정수 키
        isinstance(labels, dict) and set(map(str, labels)) == {"0", "1"}
        if labels is not None
        else width == 2
    )
    if (
        not two_labels
        or width not in (None, 2)
        or config.get("problem_type") != "single_label_classification"
    ):
        raise ClassifierShapeError("unexpected toxicity classifier shape")
    return ToxicitySettings(
        threshold, review, length, stride, positive, quantization == "int8-dynamic-channel"
    )
