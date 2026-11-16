"""#549 서비스 경계·원문 보존·실제 호출 생략을 검증한다."""

import asyncio
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.m2.content3_rule import content3_score
from app.m2.models import M2Request, M2Skipped
from app.m2.service import M2Service, infer
from app.model_loader import LoadedModel
from app.model_registry import ModelRegistry
from tests.test_content3_rule import target_model
from tests.test_m2 import Usage, body


@pytest.mark.parametrize(
    "kind,length,skipped",
    [
        ("NARRATIVE", 0, True),
        ("NARRATIVE", 9, True),
        ("NARRATIVE", 10, False),
        ("NARRATIVE", 99, False),
        ("NARRATIVE", 100, False),
        ("ESSAY", 0, True),
        ("ESSAY", 99, True),
        ("ESSAY", 100, False),
    ],
)
def test_cleaned_length_boundaries_and_usage(monkeypatch, kind, length, skipped):
    loaded = target_model(kind, "3.0" if kind == "NARRATIVE" else "3.1")
    prompt = "우리 마을의 환경을 보호하는 방법에 대해 설명해 주세요."
    text = prompt + "\n" + "가" * length
    request = M2Request(**body(inputType=kind, text=text, prompt=prompt))
    calls = []

    def predict(*_):
        calls.append(True)
        return [[2.0] * (9 if kind == "NARRATIVE" else 14)]

    monkeypatch.setattr(LoadedModel, "predict", predict)
    registry = ModelRegistry(lambda _: loaded)
    asyncio.run(registry.load(loaded.metadata))
    usage = Usage()
    service = M2Service(registry, usage)
    result = asyncio.run(service.score(request))
    assert isinstance(result, M2Skipped) is skipped
    assert len(calls) == len(usage.calls) == (0 if skipped else 1)
    assert request.text == text
    assert result.preparation.chars == length
    assert result.preparation.copied == 1
    if skipped:
        assert "scores" not in result.model_dump()
        assert result.reason == "TEXT_TOO_SHORT"
    elif kind == "NARRATIVE":
        assert ("SHORT_ANSWER" in result.preparation.notices) is (length < 100)


def test_custom_labels_and_newlines_reach_model_only(monkeypatch):
    loaded = target_model("ESSAY", "3.1")
    monkeypatch.setattr(LoadedModel, "predict", lambda *_: [[2.0] * 14])
    labels = ["내 의견", "첫 근거", "둘째 근거", "다른 생각"]
    parts = ["가" * 30, "나" * 30, "다" * 30, "라" * 30]
    text = "\n".join(f"{label}: {part}" for label, part in zip(labels, parts, strict=True))
    result = infer(loaded, M2Request(**body(inputType="ESSAY", text=text, essayLabels=labels)))
    assert result.preparation.labelsRemoved == 4
    assert loaded.tokenizer.text == "\n".join(parts)


def test_content3_uses_cleaned_text(monkeypatch):
    loaded = target_model()
    monkeypatch.setattr(LoadedModel, "predict", lambda *_: [[3.0] * 9])
    prompt = "환경 보호에 관한 의견을 자세히 설명해 보세요."
    clean = "나는 책을 읽고 새로운 생각을 기록하는 것을 좋아한다."
    request = M2Request(**body(text=prompt + "\n" + clean, prompt=prompt, keywords=["환경"]))
    result = infer(loaded, request, content3_rule_enabled=True)
    assert result.rawScores.content_3 == content3_score(3.0, clean, ["환경"])[0]
    assert loaded.tokenizer.text == clean


def test_scoreless_http_is_not_inactive_or_error(monkeypatch):
    loaded = target_model()
    monkeypatch.setattr(LoadedModel, "predict", lambda *_: pytest.fail("must not infer"))
    registry = ModelRegistry(lambda _: loaded)
    asyncio.run(registry.load(loaded.metadata))
    app = create_app()
    app.state.m2_service = M2Service(registry, Usage())
    result = TestClient(app).post(
        "/internal/m2/scores", json=body(text="몰라요"), headers={"X-Internal-Token": "test-token"}
    )
    assert result.status_code == 200
    assert result.json()["active"] is True
    assert result.json()["scored"] is False
    assert "scores" not in result.json()


def test_legacy_version_is_unchanged(monkeypatch):
    loaded = target_model(release="2.0")
    monkeypatch.setattr(LoadedModel, "predict", lambda *_: [[3.0] * 9])
    result = infer(loaded, M2Request(**body(text="몰라요")))
    assert result.preparation is None
    assert result.scores.content_3 == 3


@pytest.mark.parametrize("kind,release", [("ESSAY", "3.1"), ("NARRATIVE", "3.0")])
def test_b_cuts_immediately_below_equal_and_above(monkeypatch, kind, release):
    loaded = target_model(kind, release)
    cuts = json.loads(
        (
            Path(__file__).parents[1]
            / "metadata/1112b"
            / loaded.metadata.name
            / release
            / "score_cuts.json"
        ).read_text()
    )
    loaded = replace(loaded, score_cuts=cuts)
    request = M2Request(**body(inputType=kind, text="가" * 150))
    offset = 0 if kind == "ESSAY" else 1
    for item, boundaries in cuts.items():
        for index, cut in enumerate(boundaries):
            for raw, expected in [
                (math.nextafter(cut, -math.inf), index),
                (cut, index + 1),
                (math.nextafter(cut, math.inf), index + 1),
            ]:
                monkeypatch.setattr(
                    LoadedModel,
                    "predict",
                    lambda *_, raw=raw: [[raw] * (14 if kind == "ESSAY" else 9)],
                )
                assert infer(loaded, request).scores.model_dump()[item] == expected + offset


def test_original_short_and_removed_short_have_distinct_notices():
    loaded = target_model("ESSAY", "3.1")
    original = infer(loaded, M2Request(**body(inputType="ESSAY", text="짧은 합성 글입니다.")))
    prompt = "동네에 필요한 시설이 무엇인지 의견과 근거를 설명해 주세요."
    cleaned = infer(loaded, M2Request(**body(inputType="ESSAY", prompt=prompt, text=prompt)))
    assert original.preparation.notices == ["ESSAY_ORIGINALLY_SHORT"]
    assert "ESSAY_TOO_SHORT" in cleaned.preparation.notices


def test_copy_precedes_repeat_and_short_fragments_follow_supplier_rule():
    from app.m2.m2_text_guard import prepare_essay

    prompt = "동네에 필요한 시설을 정하고 그 이유를 자세히 설명해 주세요."
    body_text = "나는 가까운 도서관에서 책을 읽고 친구들과 함께 공부하고 싶다."
    result = prepare_essay((prompt + "\n") * 6 + "칸\n" + body_text, prompt)
    assert result.copied == 6
    assert not result.repeated
    assert result.text == body_text
