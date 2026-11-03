"""선택 보정의 경계·기존 결과 보존·설정부터 HTTP 응답까지 검증."""

import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import bootstrap
from app.config import Settings
from app.m2.content3_rule import content3_score, keyword_groups, keyword_ratio
from app.m2.models import ITEMS, M2Request
from app.m2.service import M2Service, infer
from app.model_loader import LoadedModel
from app.model_registry import ModelRegistry
from tests.test_m2 import Usage, body, modern_model
from tests.test_model_registry import version


def target_model(kind="NARRATIVE", release="3.0", scopes=None):
    old = modern_model(kind)
    meta = version(
        name=old.metadata.name,
        scopes=scopes or tuple(f"judgment/grade-{n}/{kind.lower()}" for n in (5, 6)),
        release=release,
    )
    return replace(old, metadata=meta)


@pytest.mark.parametrize(
    "keywords,expected",
    [
        (
            ["한글(훈민정음, 정음)", "환경(자연/생태)"],
            [["한글", "훈민정음", "정음"], ["환경", "자연", "생태"]],
        ),
        (["환경, 보호"], [["환경"], ["보호"]]),
        ([" 환경 ", " , ", "보호"], [["환경"], ["보호"]]),
        ([], []),
    ],
)
def test_groups_match_owner_reference(keywords, expected):
    assert keyword_groups(keywords) == expected


@pytest.mark.parametrize(
    "text,keywords,expected",
    [
        ("한 글과 훈민\n정음, 정음", ["한글(훈민정음, 정음)", "환경"], 0.5),
        ("훈 민\t정 음과 생태", ["한글(훈민정음, 정음)", "환경(자연/생태)"], 1.0),
        ("환경 보호", ["환경, 보호"], 1.0),
        ("환경", ["환경, 보호"], 0.5),
        ("바다", ["한글", "환경"], 0.0),
        ("환경", [], 0.0),
    ],
)
def test_ratio_counts_each_group_once_and_preserves_inputs(text, keywords, expected):
    before = keywords.copy()
    assert keyword_ratio(text, keywords) == expected
    assert keywords == before


@pytest.mark.parametrize(
    "model_raw,text,expected",
    [
        (3.0, "바다", (1.5634, 2)),
        (3.0, "한글", (3.008, 3)),
        (3.0, "한글 환경", (4.4525, 4)),
        (-100.0, "바다", (1.0, 1)),
        (100.0, "한글 환경", (5.0, 5)),
        ((2.5 - 0.9724) / 0.197, "바다", (2.5, 3)),
        ((2.49996 - 0.9724) / 0.197, "바다", (2.5, 2)),
    ],
)
def test_formula_clipping_and_half_up_before_display_rounding(model_raw, text, expected):
    assert content3_score(model_raw, text, ["한글", "환경"]) == expected


def test_default_off_preserves_entire_response_and_skips_rule(monkeypatch):
    loaded = target_model()
    raw = [-8, 2, 3, 4, 10, 1, 2.9, 3.9, 4.9]
    monkeypatch.setattr(LoadedModel, "predict", lambda *_: [raw])
    monkeypatch.setattr(
        "app.m2.service.content3_score", lambda *_: pytest.fail("disabled rule was called")
    )
    expected = {
        "active": True,
        "inputType": "NARRATIVE",
        "scores": dict(zip(ITEMS, [1, 2, 3, 4, 5, 1, 2, 3, 4], strict=True)),
        "rawScores": dict(zip(ITEMS, raw, strict=True)),
        "model": {"name": "m2-klue-narrative", "version": "3.0", "revision": 1},
    }
    request = M2Request(**body())
    assert infer(loaded, request).model_dump() == expected
    assert infer(loaded, request, content3_rule_enabled=False).model_dump() == expected


@pytest.mark.parametrize("grade", [5, 6])
def test_enabled_changes_only_content3_and_can_be_disabled(monkeypatch, grade):
    loaded = target_model()
    calls = []

    def predict(*_):
        calls.append(True)
        return [[3.0] * 9]

    monkeypatch.setattr(LoadedModel, "predict", predict)
    request = M2Request(
        **body(grade=grade, text="훈 민 정 음을 배웠다.", keywords=["한글(훈민정음, 정음)"])
    )
    registry = ModelRegistry(lambda _: loaded)
    asyncio.run(registry.load(loaded.metadata))
    usage = Usage()

    def score(enabled):
        return asyncio.run(
            M2Service(registry, usage, content3_rule_enabled=enabled).score(request)
        ).model_dump()

    baseline = score(False)
    corrected = score(True)
    assert corrected["rawScores"]["content_3"] == 4.4525
    assert corrected["scores"]["content_3"] == 4
    corrected["rawScores"]["content_3"] = baseline["rawScores"]["content_3"]
    corrected["scores"]["content_3"] = baseline["scores"]["content_3"]
    assert corrected == baseline == score(False)
    assert len(calls) == len(usage.calls) == 3
    assert all(call[1]["success"] for call in usage.calls)
    assert loaded.tokenizer.text == request.text
    assert loaded.tokenizer.first == f"[학년] 초{grade} [핵심어] 한글(훈민정음, 정음)"
    assert request.keywords == ["한글(훈민정음, 정음)"]


@pytest.mark.parametrize(
    "kind,release", [("NARRATIVE", "2.0"), ("NARRATIVE", "3.1"), ("ESSAY", "3.1")]
)
def test_enabled_does_not_change_other_models(monkeypatch, kind, release):
    loaded = target_model(kind, release)
    monkeypatch.setattr(LoadedModel, "predict", lambda *_: [[3.0] * (14 if kind == "ESSAY" else 9)])
    monkeypatch.setattr(
        "app.m2.service.content3_score", lambda *_: pytest.fail("out-of-target rule was called")
    )
    request = M2Request(**body(inputType=kind))
    assert infer(loaded, request, content3_rule_enabled=True) == infer(loaded, request)


@pytest.mark.parametrize("case", ["grade", "keywords", "scope", "no-model"])
def test_enabled_does_not_bypass_inactive_gate(monkeypatch, case):
    loaded = target_model(scopes=("judgment/grade-5/narrative",))
    registry = ModelRegistry(lambda _: loaded)
    if case != "no-model":
        asyncio.run(registry.load(loaded.metadata))
    monkeypatch.setattr(LoadedModel, "predict", lambda *_: pytest.fail("inactive inferred"))
    changes = {"grade": 4} if case == "grade" else {"grade": 6} if case == "scope" else {}
    if case == "keywords":
        changes["keywords"] = []
    usage = Usage()
    service = M2Service(registry, usage, content3_rule_enabled=True)
    assert asyncio.run(service.score(M2Request(**body(**changes)))).model_dump() == {
        "active": False
    }
    assert not usage.calls


@pytest.mark.parametrize("fault", ["cuts", "nan"])
def test_enabled_keeps_failure_response_and_usage(monkeypatch, fault):
    loaded = target_model()
    raw = [3.0] * 9
    if fault == "cuts":
        del loaded.score_cuts["content_3"]
    else:
        raw[4] = float("nan")
    monkeypatch.setattr(LoadedModel, "predict", lambda *_: [raw])
    registry = ModelRegistry(lambda _: loaded)
    asyncio.run(registry.load(loaded.metadata))
    usage = Usage()
    app = bootstrap.create_app()
    app.state.m2_service = M2Service(registry, usage, content3_rule_enabled=True)
    response = TestClient(app).post(
        "/internal/m2/scores", json=body(), headers={"X-Internal-Token": "test-token"}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SCORING_UNAVAILABLE"
    assert usage.calls[0][1]["success"] is False


@pytest.mark.parametrize("flag,expected", [(None, 3.0), ("false", 3.0), ("true", 4.4525)])
def test_environment_through_lifespan_to_http(monkeypatch, caplog, flag, expected):
    if flag is None:
        monkeypatch.delenv("M2_CONTENT3_RULE_ENABLED", raising=False)
    else:
        monkeypatch.setenv("M2_CONTENT3_RULE_ENABLED", flag)
    settings = Settings()
    monkeypatch.setattr(bootstrap, "get_settings", lambda: settings)
    loaded = target_model()
    registry = ModelRegistry(lambda _: loaded)
    asyncio.run(registry.load(loaded.metadata))
    monkeypatch.setattr(bootstrap, "ModelRegistry", lambda _: registry)
    monkeypatch.setattr(LoadedModel, "predict", lambda *_: [[3.0] * 9])

    class Broker:
        is_connected = False

        def __init__(self, *_):
            pass

        def start(self):
            pass

        async def close(self):
            pass

    class Consumer(Broker):
        async def is_ready(self):
            return True

    monkeypatch.setattr(bootstrap, "AmqpConnection", Broker)
    monkeypatch.setattr(bootstrap, "ModelVersionConsumer", Consumer)
    caplog.set_level("INFO", logger="app.bootstrap")
    with TestClient(bootstrap.create_app()) as client:
        response = client.post(
            "/internal/m2/scores",
            json=body(text="비공개 학생 글: 훈 민 정 음", keywords=["한글(훈민정음, 정음)"]),
            headers={"X-Internal-Token": "test-token"},
        )
    assert response.status_code == 200
    assert response.json()["rawScores"]["content_3"] == expected
    assert response.json()["scores"]["content_3"] == (4 if flag == "true" else 3)
    assert f"enabled={flag == 'true'} rule_version=1.0.0" in caplog.text
    assert "비공개 학생 글" not in caplog.text
