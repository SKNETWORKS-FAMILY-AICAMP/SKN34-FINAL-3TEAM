import argparse
import json
import pathlib

import pytest
import train as T


def args(**kw):
    base = dict(model=T.BASE_MODEL, max_length=128, epochs=3, lr=2e-5, batch_size=32, seed=42)
    return argparse.Namespace(**{**base, **kw})


def test_binary_metrics():
    probs = [0.9, 0.8, 0.2, 0.6, 0.1]
    labels = [1, 1, 1, 0, 0]
    m = T.binary_metrics(probs, labels, 0.5)
    assert m["precision"] == round(2 / 3, 4)
    assert m["recall"] == round(2 / 3, 4)
    assert m["falsePositiveRate"] == 0.5
    assert T.binary_metrics([0.1], [1], 0.5)["f1"] == 0.0


def test_read_jsonl_checks_labels(tmp_path: pathlib.Path):
    good = tmp_path / "good.jsonl"
    good.write_text('{"text": "가", "label": 1}\n{"text": "나", "label": 0}\n', encoding="utf-8")
    assert [x["label"] for x in T.read_jsonl(good)] == [1, 0]
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"text": "가", "label": 2}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        T.read_jsonl(bad)


def test_train_info_contract():
    info = T.build_train_info(
        base_revision="abc", args=args(), sizes={"train": 1}, best_epoch=2, valid={"f1": 0.8}
    )
    assert info["threshold"] == 0.5 and info["max_length"] == 128 and info["stride"] == 32
    assert info["labels"] == {"0": "ok", "1": "block"}
    with pytest.raises(ValueError):
        T.build_train_info(
            base_revision="abc", args=args(), sizes={}, best_epoch=1, valid={}, threshold=1.0
        )


def test_check_artifact(tmp_path: pathlib.Path):
    assert len(T.check_artifact(tmp_path)) == len(T.ARTIFACT_FILES)
    for name in T.ARTIFACT_FILES:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    config = {"id2label": {"0": "ok", "1": "block"}}
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    info = T.build_train_info(base_revision=None, args=args(), sizes={}, best_epoch=1, valid={})
    (tmp_path / "train_info.json").write_text(json.dumps(info), encoding="utf-8")
    assert T.check_artifact(tmp_path) == []
    info["threshold"] = 0
    (tmp_path / "train_info.json").write_text(json.dumps(info), encoding="utf-8")
    assert "threshold가 0 초과 1 미만이 아님" in T.check_artifact(tmp_path)
