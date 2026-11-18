"""답변 표현 분류 (api-spec 4.3.4·5.2·5.2.1, #691). 글은 모두 합성."""

import asyncio
import hashlib
import json
import logging
import sys
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import security
from app.bootstrap import create_app
from app.errors import ApiError
from app.model_loader import LoadedModel, ModelLoader
from app.model_registry import ModelRegistry
from app.model_versions import ActiveModelVersion, scoring_versions
from app.preflight import FILES, PreflightRequest
from app.toxicity.metadata import ClassifierShapeError, validate_toxicity
from app.toxicity.models import ToxicityRequest
from app.toxicity.service import ToxicityService, classify
from tests.test_model_registry import version
from tests.test_preflight import service as preflight_service

HEADERS = {"X-Internal-Token": "test-token"}
CONFIG = {"id2label": {"0": "ok", "1": "block"}, "problem_type": "single_label_classification"}
TRAINING = {
    "task": "toxicity-binary",
    "positiveLabel": 1,
    "max_length": 128,
    "stride": 32,
    "threshold": 0.92,
    "quantization": "int8-dynamic-channel",
}
SECRET = "합성비밀문장"


class Tokenizer:
    """글자 10개마다 창 하나. 창 i의 첫 토큰이 i라서 predict가 창을 구분할 수 있다."""

    def __call__(self, text, **kwargs):
        self.options = kwargs
        windows = len(text) // 10 + 1
        return {"input_ids": [[i, 0] for i in range(windows)], "attention_mask": [[1, 1]] * windows}


def logit(prob):
    """막을 확률 prob이 나오는 [정상, 막을 글] 로짓."""
    import math

    return [0.0, math.log(prob / (1 - prob))]


def loaded_model(name="tox-kcelectra-base", revision=1, scopes=("answer-filter",), **training):
    return LoadedModel(
        version(revision, name, scopes, "20261117"),
        SimpleNamespace(config=SimpleNamespace(to_dict=lambda: dict(CONFIG))),
        Tokenizer(),
        {**TRAINING, **training},
    )


def setup(monkeypatch, probs=None, models=None, **service_options):
    """probs: 창 번호 → 막을 확률(없으면 0.1). 호출한 묶음 크기를 calls에 남긴다."""
    probs = probs or {}
    calls = []

    def predict(self, inputs):
        ids = inputs["input_ids"]
        calls.append(len(ids))
        return [logit(probs.get(window[0], 0.1)) for window in ids]

    monkeypatch.setattr(LoadedModel, "predict", predict)
    models = models if models is not None else [loaded_model()]
    registry = ModelRegistry(lambda v: next(m for m in models if m.metadata == v))
    for item in models:
        asyncio.run(registry.load(item.metadata))
    service = ToxicityService(registry, **service_options)
    app = create_app()
    app.state.toxicity_service = service
    return TestClient(app), calls


def check(client, texts, headers=HEADERS):
    return client.post("/internal/toxicity/checks", json={"texts": texts}, headers=headers)


def test_flagged_when_any_window_reaches_threshold(monkeypatch):
    client, calls = setup(monkeypatch, probs={0: 0.95})
    response = check(client, ["짧은 합성 글"])
    assert response.status_code == 200
    assert response.json() == {
        "active": True,
        "flagged": True,
        "review": False,
        "model": {"name": "tox-kcelectra-base", "version": "20261117", "revision": 1},
    }
    assert calls == [1]


def test_normal_text_passes_without_scores_in_response(monkeypatch):
    client, _ = setup(monkeypatch, probs={0: 0.919})
    data = check(client, ["첫 칸", "둘째 칸"]).json()
    assert data["flagged"] is False and data["review"] is False
    assert set(data) == {"active", "flagged", "review", "model"}


def test_long_text_is_split_into_windows_in_batches_of_eight_and_stops_at_flag(monkeypatch):
    # 199자 → 창 20개, 창 9(둘째 묶음)에서 걸리면 셋째 묶음은 계산하지 않는다
    client, calls = setup(monkeypatch, probs={9: 0.99})
    assert check(client, ["가" * 199]).json()["flagged"] is True
    assert calls == [8, 8]


def test_tokenizer_windows_match_training_contract(monkeypatch):
    client, _ = setup(monkeypatch)
    loaded = loaded_model()
    classify(loaded, ["합성 글"], deadline=float("inf"))
    assert loaded.tokenizer.options == {
        "truncation": True,
        "max_length": 128,
        "stride": 32,
        "return_overflowing_tokens": True,
        "padding": True,
        "return_tensors": "pt",
    }


def test_review_only_when_not_flagged_and_model_has_review_threshold(monkeypatch):
    review_model = loaded_model(review_threshold=0.5)
    client, _ = setup(monkeypatch, probs={0: 0.6}, models=[review_model])
    assert check(client, ["합성 글"]).json()["review"] is True
    client, _ = setup(
        monkeypatch, probs={0: 0.6, 1: 0.95}, models=[loaded_model(review_threshold=0.5)]
    )
    data = check(client, ["가" * 15]).json()
    assert data["flagged"] is True and data["review"] is False
    client, _ = setup(monkeypatch, probs={0: 0.6})
    assert check(client, ["합성 글"]).json()["review"] is False


@pytest.mark.parametrize(
    "models",
    [
        [],
        [loaded_model(scopes=("judgment/grade-5/narrative",))],
    ],
)
def test_inactive_without_active_model_or_scope(monkeypatch, models):
    client, calls = setup(monkeypatch, models=models)
    assert check(client, ["합성 글"]).json() == {"active": False}
    assert calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"texts": []},
        {"texts": ["가"] * 21},
        {"texts": ["   "]},
        {"texts": ["가" * 1000, "나" * 501]},
        {"texts": ["가"], "threshold": 0.1},
        {"texts": "가"},
    ],
)
def test_validation_400(monkeypatch, body):
    client, calls = setup(monkeypatch)
    response = client.post("/internal/toxicity/checks", json=body, headers=HEADERS)
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert calls == []


def test_exact_limits_are_accepted():
    ToxicityRequest(texts=["가"] * 20)
    ToxicityRequest(texts=["가" * 1000, "나" * 500])


def test_only_learning_caller_is_allowed(monkeypatch):
    client, _ = setup(monkeypatch)
    base = security.get_settings()
    tokens = {"internal_token_" + c.replace("-", "_"): c + "-token" for c in security.CALLER_PATHS}
    monkeypatch.setattr(security, "get_settings", lambda: base.model_copy(update=tokens))
    assert check(client, ["합성 글"], {"X-Internal-Token": "learning-token"}).status_code == 200
    assert check(client, ["합성 글"], {"X-Internal-Token": "ai-token"}).status_code == 403
    assert check(client, ["합성 글"], {"X-Internal-Token": "wrong"}).status_code == 401
    assert check(client, ["합성 글"], {}).status_code == 401
    assert not security.caller_permits("learning", "/internal/m2/scores")


def test_deadline_and_failure_are_503_not_inactive_and_logs_have_no_text(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client, calls = setup(monkeypatch, deadline=0.0)
    response = check(client, [SECRET])
    assert response.status_code == 503
    assert response.json()["code"] == "SCORING_UNAVAILABLE"
    assert calls == []

    def broken(self, inputs):
        raise RuntimeError(SECRET)

    client, _ = setup(monkeypatch)
    monkeypatch.setattr(LoadedModel, "predict", broken)
    assert check(client, [SECRET]).status_code == 503
    assert SECRET not in caplog.text
    assert "result=DEADLINE" in caplog.text and "error_type=RuntimeError" in caplog.text


def test_multiple_active_toxicity_models_are_503(monkeypatch):
    models = [loaded_model("tox-a"), loaded_model("tox-b")]
    client, calls = setup(monkeypatch, models=models)
    assert check(client, ["합성 글"]).status_code == 503
    assert calls == []


def test_separate_gate_times_out_without_blocking_m2(monkeypatch):
    async def run():
        start, finish = threading.Event(), threading.Event()
        loaded = loaded_model()
        registry = ModelRegistry(lambda _: loaded)
        await registry.load(loaded.metadata)

        def predict(self, inputs):
            start.set()
            assert finish.wait(3)
            return [logit(0.1)] * len(inputs["input_ids"])

        monkeypatch.setattr(LoadedModel, "predict", predict)
        service = ToxicityService(registry, queue_timeout=0.01)
        task = asyncio.create_task(service.check(ToxicityRequest(texts=["합성 글"])))
        for _ in range(100):
            if start.is_set():
                break
            await asyncio.sleep(0.005)
        assert start.is_set()
        with pytest.raises(ApiError) as error:
            await service.check(ToxicityRequest(texts=["합성 글"]))
        assert error.value.status == 503
        finish.set()
        assert (await task).flagged is False

    asyncio.run(run())


def test_scoring_snapshot_accepts_tox_models():
    item = version(1, "tox-kcelectra-base", ("answer-filter",), "20261117").model_dump(
        by_alias=True, mode="json"
    )
    assert [v.name for v in scoring_versions({"items": [item]})] == ["tox-kcelectra-base"]
    with pytest.raises(ValueError):
        ActiveModelVersion.model_validate({**item, "name": "tx-other"})


@pytest.mark.parametrize(
    "change",
    [
        {"threshold": None},
        {"threshold": 1},
        {"threshold": 0},
        {"threshold": True},
        {"review_threshold": 0.92},
        {"review_threshold": 0},
        {"max_length": "128"},
        {"stride": 126},
        {"positiveLabel": 2},
        {"quantization": "int4"},
        {"quantization": "int8-dynamic"},
    ],
)
def test_training_metadata_is_rejected(change):
    training = {k: v for k, v in {**TRAINING, **change}.items() if v is not None}
    with pytest.raises(ValueError):
        validate_toxicity(training, CONFIG)


@pytest.mark.parametrize(
    "config",
    [
        {"id2label": {"0": "a"}, "problem_type": "single_label_classification"},
        {"id2label": {"0": "ok", "1": "block"}, "problem_type": "regression"},
        {"num_labels": 3, "problem_type": "single_label_classification"},
    ],
)
def test_regression_or_wrong_width_is_rejected(config):
    with pytest.raises(ClassifierShapeError):
        validate_toxicity(TRAINING, config)


def test_valid_metadata_without_optional_fields():
    settings = validate_toxicity({"threshold": 0.5, "max_length": 64, "stride": 16}, CONFIG)
    assert (settings.positive, settings.int8, settings.review_threshold) == (1, False, None)


class FakeClassifier:
    def __init__(self, config):
        self.config = SimpleNamespace(**config, to_dict=lambda: dict(config))
        self.config.num_labels = len(config.get("id2label", {})) or config.get("num_labels")

    def to(self, device):
        return self

    def eval(self):
        return self


def load_tox(tmp_path, monkeypatch, training, config=CONFIG):
    (tmp_path / "train_info.json").write_text(json.dumps(training))
    model = FakeClassifier(config)
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoModelForSequenceClassification=SimpleNamespace(
                from_pretrained=lambda *a, **kw: (model, {})
            ),
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **kw: object()),
        ),
    )

    class Artifacts:
        @contextmanager
        def download(self, uri):
            yield tmp_path

    return model, ModelLoader(Artifacts())(version(1, "tox-kcelectra-base", ("answer-filter",)))


def test_loader_quantizes_only_when_training_info_says_int8(tmp_path, monkeypatch):
    import torch

    quantized = []
    monkeypatch.setattr(
        torch.ao.quantization,
        "quantize_dynamic",
        lambda model, spec, dtype: quantized.append((spec, dtype)) or model,
    )
    _, loaded = load_tox(tmp_path, monkeypatch, TRAINING)
    from torch.ao.quantization import per_channel_dynamic_qconfig

    assert quantized == [({torch.nn.Linear: per_channel_dynamic_qconfig}, torch.qint8)]
    assert loaded.score_cuts is None and loaded.training_config["threshold"] == 0.92
    load_tox(tmp_path, monkeypatch, {**TRAINING, "quantization": "none"})
    assert len(quantized) == 1


@pytest.mark.parametrize(
    "training,config",
    [
        ({k: v for k, v in TRAINING.items() if k != "threshold"}, CONFIG),
        (TRAINING, {**CONFIG, "problem_type": "regression"}),
    ],
)
def test_loader_rejects_regression_or_missing_threshold(tmp_path, monkeypatch, training, config):
    with pytest.raises(ValueError):
        load_tox(tmp_path, monkeypatch, training, config)


def tox_preflight(files=None, training=TRAINING, config=CONFIG):
    names = files or sorted(FILES - {"score_cuts.json"})
    contents = {f: b"synthetic" for f in names}
    contents["config.json"] = json.dumps(config).encode()
    contents["train_info.json"] = json.dumps(training).encode()
    request = {
        "name": "tox-kcelectra-base",
        "version": "20261117",
        "artifactUri": "s3://models/models/tox-kcelectra-base/20261117/",
        "files": [
            {
                "file": f,
                "bytes": len(contents[f]),
                "sha256": hashlib.sha256(contents[f]).hexdigest(),
            }
            for f in names
        ],
    }
    return contents, request


def test_preflight_tox_five_files_pass_and_metadata_is_checked():
    contents, request = tox_preflight()
    checker, storage = preflight_service(contents)
    result = checker.check(PreflightRequest(**request))
    assert result.status == "PASS" and len(result.files) == 5
    assert set(storage.reads) == {"config.json", "train_info.json"}
    contents, request = tox_preflight(config={**CONFIG, "problem_type": "regression"})
    assert preflight_service(contents)[0].check(PreflightRequest(**request)).code == (
        "OUTPUT_MISMATCH"
    )
    contents, request = tox_preflight(training={**TRAINING, "review_threshold": 0.95})
    assert preflight_service(contents)[0].check(PreflightRequest(**request)).code == (
        "INVALID_METADATA"
    )


def test_preflight_file_set_depends_on_name_prefix():
    _, request = tox_preflight(files=sorted(FILES))
    with pytest.raises(ValueError):
        PreflightRequest(**request)
    _, request = tox_preflight()
    with pytest.raises(ValueError):
        PreflightRequest(**{**request, "name": "m2-klue-narrative"})
    contents, request = tox_preflight()
    result = preflight_service(contents)[0].check(PreflightRequest(**{**request, "name": "tox-"}))
    assert result.code == "UNSUPPORTED_MODEL"


def test_real_tiny_model_matches_ml_tox_window_scoring(tmp_path):
    """학습·평가(ml/tox eval.py score_texts)와 같은 창 나누기·최댓값이어야 임계값이 맞는다."""
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    tokenizers = pytest.importorskip("tokenizers")
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"] + [chr(0xAC00 + i) for i in range(30)]
    core = tokenizers.Tokenizer(
        tokenizers.models.WordPiece({t: i for i, t in enumerate(vocab)}, unk_token="[UNK]")
    )
    core.pre_tokenizer = tokenizers.pre_tokenizers.Split("", "isolated")
    core.post_processor = tokenizers.processors.TemplateProcessing(
        single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 2), ("[SEP]", 3)]
    )
    tokenizer = transformers.PreTrainedTokenizerFast(
        tokenizer_object=core, pad_token="[PAD]", cls_token="[CLS]", sep_token="[SEP]"
    )
    torch.manual_seed(0)
    config = transformers.ElectraConfig(
        vocab_size=len(vocab),
        embedding_size=8,
        hidden_size=8,
        num_hidden_layers=1,
        num_attention_heads=1,
        intermediate_size=16,
        max_position_embeddings=64,
        num_labels=2,
        problem_type="single_label_classification",
    )
    model = transformers.ElectraForSequenceClassification(config).eval()
    training = {"threshold": 0.5, "max_length": 16, "stride": 4}
    loaded = LoadedModel(version(1, "tox-tiny", ("answer-filter",)), model, tokenizer, training)
    text = "".join(vocab[5 + i % 30] for i in range(100))
    enc = tokenizer(
        [text],
        truncation=True,
        max_length=16,
        stride=4,
        return_overflowing_tokens=True,
        padding=True,
        return_tensors="pt",
    )
    with torch.no_grad():
        logits = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]).logits
    expected = torch.softmax(logits.float(), dim=-1)[:, 1].max().item()
    assert len(enc["input_ids"]) > 8  # 묶음 두 개 이상
    assert classify(loaded, [text], float("inf"))[0] is (expected >= 0.5)
    assert (
        classify(
            LoadedModel(
                loaded.metadata, model, tokenizer, {**training, "threshold": expected - 1e-6}
            ),
            [text],
            float("inf"),
        )[0]
        is True
    )
    assert (
        classify(
            LoadedModel(
                loaded.metadata,
                model,
                tokenizer,
                {**training, "threshold": min(expected + 1e-4, 0.99)},
            ),
            [text],
            float("inf"),
        )[0]
        is False
    )
