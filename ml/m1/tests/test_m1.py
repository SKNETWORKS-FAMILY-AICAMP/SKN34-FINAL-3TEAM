"""71716 실제 구조를 흉내 낸 zip으로 eda·prepare·evaluate 확인 + 평문화·모델 입력·모델 구조 (#263).

로컬 MVP의 tests/test_m1.py에서 앱 연결 테스트(pipeline·report·db)를 뺀 것.
AI Hub 데이터 없이 가짜 데이터만 사용
"""

import csv
import json
import zipfile

from mathtext import latex_to_text, model_input
from model import build_model


def test_latex_to_text():
    assert latex_to_text(r"$9\frac{12}{30}+8 \frac{25}{30}$") == "9 12/30 +8 25/30"
    assert latex_to_text(r"$\begin{array} {r} 34\\ 15\\ \hline 19 \end{array}$") == "34 / 15 / 19"
    assert latex_to_text(r"$3 \times 4 \div 2$ 몇 $\text{kg}$") == "3 × 4 ÷ 2 몇 kg"
    assert latex_to_text("<table><tr><td>짬뽕</td></tr></table>") == "짬뽕"
    a, b = model_input("남은 피자는?", "$\\frac{3}{8}$", "8-5=3")
    assert a == "문제: 남은 피자는? / 정답: 3/8" and b == "8-5=3"


def _item(gid, qid, grade, correct, req=1, acc=0, sol="$34-15=19$"):
    return {
        "question_filename": f"{grade}_1_01_{gid}_{qid}.png",
        "id": f"{gid}_{qid}",
        "question_info": [
            {"question_grade": grade, "question_unit": "01", "question_topic_name": "덧셈"}
        ],
        "OCR_info": [{"figure_text": None, "question_text": "$34$에서 $15$를 뺀 수"}],
        "answer_info": [
            {
                "answer_text": "$34-15=19$",
                "answer_required_num": 1,
                "answer_bbox": [{"type": "line", "text": None}, {"type": "answer", "text": "$19$"}],
            }
        ],
        "explanation_info": [
            {
                "explanation_text": sol,
                "explanation_correct": correct,
                "explanation_error_required": req,
                "explanation_error_clac_acc": acc,
                "explanation_error_clac_num": 0,
                "explanation_difficulty": 2,
            }
        ],
    }


def _make_zips(root):
    root.mkdir()
    for prefix, groups in (("TL_3", range(0, 40)), ("VL_3", range(0, 10))):
        with zipfile.ZipFile(root / f"{prefix}.손글씨풀이_초등학교_5학년.zip", "w") as z:
            for g in groups:
                for k in range(2):
                    qid = (1000 if prefix == "VL_3" else 0) + g * 10 + k
                    c = k % 2
                    z.writestr(
                        f"P5_{g}_{qid}_{'X' if c else 'O'}.json",
                        (
                            "﻿"
                            + json.dumps(_item(9000 + g, qid, "P5", c, acc=c), ensure_ascii=False)
                        ).encode("utf-8"),
                    )
    # 원천(이미지) zip은 무시해야 함
    with zipfile.ZipFile(root / "TS_3.손글씨풀이_초등학교_5학년.zip", "w") as z:
        z.writestr("a.png", b"x")


def test_eda_prepare_evaluate_on_fake_zips(tmp_path, monkeypatch):
    import eda
    import evaluate
    import prepare

    raw = tmp_path / "raw"
    _make_zips(raw)
    monkeypatch.setattr(eda, "REPORT_DIR", tmp_path / "rep")
    monkeypatch.setattr(prepare, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(evaluate, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(evaluate, "REPORT_DIR", tmp_path / "rep")

    assert eda.main(raw) == 0
    rep = (tmp_path / "rep" / "eda_71716.md").read_text(encoding="utf-8")
    assert "풀이 레코드 100건" in rep and "모두 일치" in rep
    assert "그룹 id 겹침 (Training∩Validation): 10 / 10" in rep

    assert prepare.main(raw) == 0
    with open(tmp_path / "work" / "records.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 100
    assert (
        rows[0]["input_a"] == "문제: 34 에서 15 를 뺀 수 / 정답: 19"
        and rows[0]["input_b"] == "34-15=19"
    )
    by_group = {}
    for r in rows:
        by_group.setdefault(r["group_id"], set()).add(r["split"])
    assert all(len(s) == 1 for s in by_group.values())  # 그룹이 두 분할에 걸치지 않음

    assert evaluate.main(["--split", "train", "--model", str(tmp_path / "no_model")]) == 0
    assert "규칙(정답 숫자가 풀이에 있음)" in (tmp_path / "rep" / "eval_m1.md").read_text(
        encoding="utf-8"
    )


def test_model_ignores_segment_ids_when_encoder_has_one_type():
    """klue/roberta-base(type_vocab_size=1)에 두 문장 입력을 넣어도
    IndexError가 나지 않아야 한다."""
    import pytest

    torch = pytest.importorskip("torch")
    tf = pytest.importorskip("transformers")
    enc = tf.BertModel(
        tf.BertConfig(
            vocab_size=50,
            hidden_size=16,
            num_hidden_layers=1,
            num_attention_heads=2,
            intermediate_size=32,
            type_vocab_size=1,
        )
    )
    model = build_model(enc, 2)
    ids = torch.tensor([[2, 5, 3, 7, 3]])
    out = model(
        input_ids=ids,
        attention_mask=torch.ones_like(ids),
        token_type_ids=torch.tensor([[0, 0, 0, 1, 1]]),
    )
    assert [o.shape[-1] for o in out] == [2, 2, 2]


def test_eda_report_is_written_to_uncommitted_folder():
    """EDA 리포트의 예시 절에는 AI Hub 풀이 원문이 있어
    커밋하는 results/가 아닌 work/ 아래에 씀 (NFR-DAT-03)."""
    import common
    import eda

    assert eda.REPORT_DIR == common.EDA_REPORT_DIR
    assert common.EDA_REPORT_DIR.is_relative_to(common.WORK_DIR)
    assert not common.EDA_REPORT_DIR.is_relative_to(common.REPORT_DIR)
