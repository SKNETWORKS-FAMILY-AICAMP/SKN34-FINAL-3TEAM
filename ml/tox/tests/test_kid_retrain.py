import json

import make_data_kid
import pytest
import teacher_probs


def test_teacher_digest_changes_with_text_order():
    a = teacher_probs.texts_digest(["가", "나"])
    assert a == teacher_probs.texts_digest(["가", "나"])
    assert a != teacher_probs.texts_digest(["나", "가"])


def test_make_data_kid_needs_original_train_rows(tmp_path):
    src = tmp_path / "processed"
    src.mkdir()
    row = json.dumps({"text": "짧은 글", "label": 0}, ensure_ascii=False)
    (src / "train.jsonl").write_text(row + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        make_data_kid.main(["--src", str(src), "--data", str(tmp_path)])
