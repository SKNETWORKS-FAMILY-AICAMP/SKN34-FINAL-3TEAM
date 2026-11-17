import pathlib

import prepare_data as P
import pytest


def test_kmhas_label():
    assert P.kmhas_label("8") == 0
    assert P.kmhas_label("3") == 1
    assert P.kmhas_label("2,5") == 1
    assert P.kmhas_label("8,3") == 1
    with pytest.raises(ValueError):
        P.kmhas_label("9")


def test_beep_label():
    assert P.beep_label("hate") == 1
    assert P.beep_label("offensive") == 1
    assert P.beep_label("none") == 0
    with pytest.raises(ValueError):
        P.beep_label("?")


def test_dedup_drops_conflicts_and_repeats():
    rows = [
        {"text": "가", "label": 1, "source": "a"},
        {"text": "가", "label": 1, "source": "b"},
        {"text": "나", "label": 0, "source": "a"},
        {"text": "나", "label": 1, "source": "b"},
        {"text": "", "label": 0, "source": "a"},
        {"text": "다", "label": 0, "source": "a"},
    ]
    out, removed = P.dedup(rows)
    assert [x["text"] for x in out] == ["가", "다"]
    assert removed == 4


def _write(path: pathlib.Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_removes_train_overlap(tmp_path):
    k, b = tmp_path / "k", tmp_path / "b"
    _write(k / "kmhas_train.txt", "document\tlabel\n같은 글\t3\n학습만\t8\n")
    _write(k / "kmhas_valid.txt", "document\tlabel\n같은  글\t3\n")
    _write(k / "kmhas_test.txt", "document\tlabel\n시험\t8\n")
    _write(
        b / "train.tsv", "comments\tcontain_gender_bias\tbias\thate\n비프\tFalse\tnone\toffensive\n"
    )
    _write(b / "dev.tsv", "comments\tcontain_gender_bias\tbias\thate\n검증\tFalse\tnone\tnone\n")
    r = P.build(k, b)
    assert [x["text"] for x in r["splits"]["train"]] == ["학습만", "비프"]
    assert r["removed"]["trainOverlap"] == 1
    assert {x["text"] for x in r["splits"]["valid"]} == {"같은 글", "검증"}
