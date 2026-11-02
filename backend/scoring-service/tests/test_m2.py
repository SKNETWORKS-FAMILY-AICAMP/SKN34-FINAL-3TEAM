import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.errors import ApiError
from app.m2.models import ITEMS, M2Request
from app.m2.service import M2Service, infer
from app.messaging.publisher import EventPublisher, UsagePublisher
from app.model_loader import LoadedModel
from app.model_registry import ModelRegistry
from tests.test_model_registry import version


class Tokenizer:
    def __call__(self, first, text=None, **kwargs):
        self.first, self.text, self.options = first, text, kwargs
        if text is None:
            return {"input_ids": [1] * (600 if first.endswith("LONG") else 10)}
        return {"input_ids": [[1]], "attention_mask": [[1]]}

    def num_special_tokens_to_add(self, pair):
        return 4


def model(kind="NARRATIVE", revision=1, scopes=None):
    name = "m2-klue-narrative" if kind == "NARRATIVE" else "m2-klue-essay"
    meta = version(revision, name, scopes or (f"judgment/grade-5/{kind.lower()}",), "2.0")
    result = LoadedModel(
        meta,
        None,
        Tokenizer(),
        {
            "head": "reg",
            "dataset": "descriptive" if kind == "NARRATIVE" else "essay",
            "max_length": "512",
            "with_keyword": str(kind == "NARRATIVE"),
            "with_purpose": "False",
            "with_exemplar": "False",
        },
        {item: [2.0, 3.0, 4.0][:3] if item == "hol" else [2.0, 3.0, 4.0, 5.0] for item in ITEMS},
    )
    return result


def body(**changes):
    return {
        "prompt": "합성 지시문",
        "text": "합성 학생 글",
        "grade": 5,
        "inputType": "NARRATIVE",
        "keywords": ["통일성", "주제"],
        **changes,
    }


class Usage:
    def __init__(self):
        self.calls = []

    def submit(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def setup(monkeypatch, kind="NARRATIVE", scopes=None, raw=None):
    loaded = model(kind, scopes=scopes)
    monkeypatch.setattr(LoadedModel, "predict", lambda self, inputs: [raw or [3.0] * 9])
    registry = ModelRegistry(lambda _: loaded)
    asyncio.run(registry.load(loaded.metadata))
    usage = Usage()
    service = M2Service(registry, usage)
    app = create_app()
    app.state.m2_service = service
    return TestClient(app), service, loaded, usage


def test_calibration_boundaries_raw_scores_and_input(monkeypatch):
    client, _, loaded, usage = setup(monkeypatch, raw=[-8, 2, 3, 4, 10, 1, 2.9, 3.9, 4.9])
    r = client.post("/internal/m2/scores", json=body(), headers={"X-Internal-Token": "test-token"})
    assert r.status_code == 200
    data = r.json()
    assert list(data["scores"].values()) == [1, 2, 3, 4, 5, 1, 2, 3, 4]
    assert data["rawScores"]["hol"] == -8
    assert data["model"] == {"name": "m2-klue-narrative", "version": "2.0", "revision": 1}
    assert loaded.tokenizer.first == "[학년] 초5 [지시문] 합성 지시문 [핵심어] 통일성,주제"
    assert loaded.tokenizer.options["truncation"] == "only_second"
    assert usage.calls[0][1]["success"] is True


@pytest.mark.parametrize(
    "changes", [{"grade": 3}, {"grade": 4}, {"keywords": []}, {"grade": 6}, {"inputType": "ESSAY"}]
)
def test_inactive_never_predicts_or_emits(monkeypatch, changes):
    client, _, _, usage = setup(monkeypatch)

    def fail(*_):
        pytest.fail("inactive called predict")

    monkeypatch.setattr(LoadedModel, "predict", fail)
    r = client.post(
        "/internal/m2/scores", json=body(**changes), headers={"X-Internal-Token": "test-token"}
    )
    assert r.json() == {"active": False}
    assert not usage.calls


def test_essay_without_keywords_and_exact_scope(monkeypatch):
    _, service, loaded, _ = setup(monkeypatch, "ESSAY")
    assert asyncio.run(service.score(M2Request(**body(inputType="ESSAY", keywords=[])))).active
    assert "핵심어" not in loaded.tokenizer.first
    _, service, _, _ = setup(monkeypatch, scopes=("judgment/grade-5/narrative/other",))
    assert not asyncio.run(service.score(M2Request(**body()))).active


@pytest.mark.parametrize(
    "changes",
    [
        {"grade": True},
        {"grade": "5"},
        {"grade": 7},
        {"text": " "},
        {"prompt": ""},
        {"keywords": "word"},
        {"keywords": [""]},
        {"keywords": None},
        {"inputType": "SOLUTION_STEPS"},
        {"extra": "raw"},
    ],
)
def test_validation_400(monkeypatch, changes):
    client, _, _, _ = setup(monkeypatch)
    r = client.post(
        "/internal/m2/scores", json=body(**changes), headers={"X-Internal-Token": "test-token"}
    )
    assert r.status_code == 400
    assert r.headers["content-type"] == "application/problem+json"


def test_missing_token():
    r = TestClient(create_app()).post("/internal/m2/scores", json=body())
    assert r.status_code == 401


@pytest.mark.parametrize("raw,expected", [(-100.0, 1), (100.0, 4), (2.0, 2), (3.0, 3)])
def test_holistic_cuts_and_supported_grade_six(monkeypatch, raw, expected):
    _, service, _, _ = setup(monkeypatch, scopes=("judgment/grade-6/narrative",), raw=[raw] * 9)
    result = asyncio.run(service.score(M2Request(**body(grade=6))))
    assert result.active and result.scores.hol == expected


def test_missing_cuts_does_not_fall_back_to_rounding(monkeypatch):
    _, service, loaded, _ = setup(monkeypatch)
    loaded.score_cuts.clear()
    with pytest.raises(ApiError) as error:
        asyncio.run(service.score(M2Request(**body())))
    assert error.value.status == 503


@pytest.mark.parametrize("failure", ["raise", "nan", "shape", "cuts", "metadata"])
def test_failure_503_not_inactive_no_raw_logs(monkeypatch, caplog, failure):
    client, _, loaded, usage = setup(monkeypatch)
    if failure == "cuts":
        loaded.score_cuts["hol"] = [3, 2, 1]
    elif failure == "metadata":
        loaded.training_config["with_exemplar"] = "True"
    else:

        def predict(*_):
            if failure == "raise":
                raise RuntimeError("PRIVATE_STUDENT_TEXT")
            return [[float("nan")] * 9] if failure == "nan" else [[3.0]]

        monkeypatch.setattr(LoadedModel, "predict", predict)
    r = client.post(
        "/internal/m2/scores",
        json=body(text="PRIVATE_STUDENT_TEXT"),
        headers={"X-Internal-Token": "test-token"},
    )
    assert r.status_code == 503 and r.json()["code"] == "SCORING_UNAVAILABLE"
    assert "PRIVATE_STUDENT_TEXT" not in r.text + caplog.text
    assert usage.calls[0][1]["success"] is False


def test_long_first_segment_is_400(monkeypatch):
    _, _, loaded, _ = setup(monkeypatch, "ESSAY")
    with pytest.raises(ApiError) as error:
        infer(loaded, M2Request(**body(inputType="ESSAY", prompt="LONG")))
    assert error.value.status == 400


def test_nonblocking_and_version_snapshot(monkeypatch):
    async def run():
        start, finish = threading.Event(), threading.Event()
        old = model()
        new = model(revision=2)
        registry = ModelRegistry(lambda v: old if v.revision == 1 else new)
        await registry.load(old.metadata)

        def predict(self, inputs):
            start.set()
            assert finish.wait(3)
            return [[3.0] * 9]

        monkeypatch.setattr(LoadedModel, "predict", predict)
        service = M2Service(registry, Usage(), queue_timeout=0.01)
        task = asyncio.create_task(service.score(M2Request(**body())))
        for _ in range(100):
            if start.is_set():
                break
            await asyncio.sleep(0.005)
        assert start.is_set()
        await registry.load(new.metadata)
        with pytest.raises(ApiError) as error:
            await service.score(M2Request(**body()))
        assert error.value.status == 503
        finish.set()
        assert (await task).model.revision == 1
        assert (await service.score(M2Request(**body()))).model.revision == 2

    asyncio.run(run())


def test_usage_schema_and_disconnected_broker():
    class Publisher:
        async def publish(self, envelope, routing_key):
            self.envelope, self.key = envelope, routing_key
            return True

        async def close(self):
            pass

    async def run():
        publisher = Publisher()
        usage = UsagePublisher(publisher, "scoring", "scoring-service")
        usage.submit(
            "M2",
            "m2-klue-essay@2.0",
            input_tokens=None,
            output_tokens=None,
            latency_ms=12,
            success=False,
            error_code="SCORING_UNAVAILABLE",
        )
        await usage.close()
        root = Path(__file__).resolve().parents[3] / "contracts/events"
        data = publisher.envelope.model_dump(mode="json", by_alias=True)
        for filename, value in [
            ("envelope.schema.json", data),
            ("llm.usage.recorded.v1.schema.json", data["data"]),
        ]:
            jsonschema.validate(value, json.loads((root / filename).read_text(encoding="utf-8")))
        assert data["data"]["inputTokens"] is None
        assert publisher.key == "llm.usage.recorded"
        down = UsagePublisher(
            EventPublisher(SimpleNamespace(is_connected=False)), "scoring", "scoring-service"
        )
        down.submit(
            "M2",
            "m2-klue-essay@2.0",
            input_tokens=None,
            output_tokens=None,
            latency_ms=1,
            success=True,
        )
        await down.close()

    asyncio.run(run())
