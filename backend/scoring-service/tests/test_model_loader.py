import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.model_loader import LoadedModel, ModelLoader
from tests.test_model_registry import version


class FakeModel:
    config = SimpleNamespace(num_labels=9, problem_type="regression")

    def to(self, device):
        assert device == "cpu"
        return self

    def eval(self):
        return self


def test_loader_uses_local_cpu_checkpoint_and_preserves_training_files(tmp_path, monkeypatch):
    (tmp_path / "train_info.json").write_text(json.dumps({"max_length": "512"}))
    (tmp_path / "score_cuts.json").write_text(json.dumps({"holistic": [1.5, 2.5, 3.5]}))
    calls = []

    def model_load(path, **kwargs):
        calls.append(kwargs)
        assert path == tmp_path
        return FakeModel(), {}

    def tokenizer_load(path, **kwargs):
        calls.append(kwargs)
        assert path == tmp_path
        return object()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoModelForSequenceClassification=SimpleNamespace(from_pretrained=model_load),
            AutoTokenizer=SimpleNamespace(from_pretrained=tokenizer_load),
        ),
    )

    class Artifacts:
        @contextmanager
        def download(self, uri):
            assert uri == version().artifact_uri
            yield tmp_path

    model = ModelLoader(Artifacts())(version())
    assert model.metadata == version()
    assert model.training_config["max_length"] == "512"
    assert model.score_cuts == {"holistic": [1.5, 2.5, 3.5]}
    assert all(call["local_files_only"] and not call["trust_remote_code"] for call in calls)
    assert calls[1]["use_safetensors"]


@pytest.mark.parametrize("fault", ["missing_weights", "wrong_head"])
def test_incomplete_checkpoint_not_published(tmp_path, monkeypatch, fault):
    model = FakeModel()
    if fault == "wrong_head":
        model.config = SimpleNamespace(num_labels=2, problem_type="regression")
    info = {"missing_keys": ["classifier.weight"]} if fault == "missing_weights" else {}
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoModelForSequenceClassification=SimpleNamespace(
                from_pretrained=lambda *a, **kw: (model, info)
            ),
            AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **kw: object()),
        ),
    )

    class Artifacts:
        @contextmanager
        def download(self, uri):
            yield tmp_path

    with pytest.raises(ValueError):
        ModelLoader(Artifacts())(version())


def test_m1_not_silently_loaded_as_m2():
    with pytest.raises(ValueError, match="not available"):
        ModelLoader(None)(version(name="m1-math"))


def test_predict_is_sync_cpu_and_never_passes_token_type_ids():
    import inspect

    import torch

    seen = []

    def predict(**kwargs):
        assert not torch.is_grad_enabled()
        seen.append(kwargs)
        return SimpleNamespace(logits=torch.ones((1, 9)))

    model = LoadedModel(version(), predict, None, {})
    assert not inspect.iscoroutinefunction(model.predict)
    assert model.predict(
        {
            "input_ids": torch.tensor([[1, 2]]),
            "attention_mask": torch.tensor([[1, 1]]),
            "token_type_ids": torch.tensor([[1, 1]]),
        }
    ) == [[1.0] * 9]
    assert set(seen[0]) == {"input_ids", "attention_mask"}
    assert all(value.device.type == "cpu" for value in seen[0].values())
