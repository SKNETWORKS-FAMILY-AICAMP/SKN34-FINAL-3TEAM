"""ml/m2 스크립트 단위 테스트 (이슈 #142). 합성 데이터만 쓴다 — AI Hub 원본·학생 글 없음.

실행: cd ml/m2 && uv run pytest
torch가 없는 환경(CI)에서는 train_545 관련 테스트만 건너뛴다.
"""

import baseline
import clean_data
import numpy as np
import pandas as pd
import pytest
import split


# ---------- 데이터 나누기: 같은 문항이 두 세트에 들어가면 안 됨 (누수) ----------
def _answers(n_prompts=40, per_prompt=5):
    rows = []
    grades = ["초5", "초6", "중1", "중2"]
    subjects = ["국어", "사회", "과학", "도덕", "기타"]
    for i in range(n_prompts):
        for k in range(per_prompt):
            rows.append(
                {
                    "prompt_id": f"P{i:03d}",
                    "grade": grades[i % 4],
                    "subject": subjects[i % 5],
                    "essay_type": ["설명", "주장", "정서"][i % 3],
                    "answer_id": f"P{i:03d}_{k}",
                }
            )
    return pd.DataFrame(rows)


@pytest.mark.parametrize("fn", [split.split_descriptive, split.split_essay])
def test_split_one_set_per_prompt(fn, tmp_path):
    df = _answers()
    prompts = fn(df, seed=42)
    assert prompts["prompt_id"].is_unique
    assert set(prompts["split_new"]) <= {"train", "valid", "test"}
    merged = df.merge(prompts[["prompt_id", "split_new"]], on="prompt_id")
    assert merged.groupby("prompt_id")["split_new"].nunique().max() == 1
    split.check_and_save(df, prompts, tmp_path / "s.csv")  # 누수면 AssertionError


def test_split_same_seed_same_result():
    df = _answers()
    a = split.split_essay(df, seed=42).sort_values("prompt_id").reset_index(drop=True)
    b = split.split_essay(df, seed=42).sort_values("prompt_id").reset_index(drop=True)
    assert a.equals(b)


# ---------- 정제: 가림 표시·공백, 중복은 평가 쪽 1건만 ----------
def test_clean_text_removes_marker_and_spaces():
    s = pd.Series(["가나 #@이름01# 다라", "  공백   많음  ", None])
    out, stats = clean_data.clean_text(s, clean_data.DEFAULT_MARKER, "")
    assert "#@" not in out.iloc[0]
    assert out.iloc[1] == "공백 많음"
    assert out.iloc[2] == ""
    assert stats["표시 바꾼·지운 답"] == 1


def test_dedupe_keeps_eval_side_and_averages():
    df = pd.DataFrame(
        {
            "split": ["TL", "VL", "TL"],
            "text": ["같은 글", "같은  글", "다른 글"],
            "org_r1": [1.0, 3.0, 2.0],
        }
    )
    kept, stats = clean_data.dedupe(df, eval_value="VL", average=True)
    assert len(kept) == 2
    assert stats["뺀 답"] == 1
    same = kept[kept["text"].str.startswith("같은")]
    assert same["split"].item() == "VL"  # 평가 쪽을 남김 → 학습·평가 걸침 없음
    assert same["org_r1"].item() == 2.0  # 점수는 묶음 평균


# ---------- 정답 반올림: 두 전문가 평균 x.5는 올림 ----------
def test_gold_rounds_half_up():
    d = pd.DataFrame({"hol_r1": [2, 3, 1], "hol_r2": [3, 3, 2]})
    assert baseline.gold(d, "hol").tolist() == [3, 3, 2]


# ---------- 예측 CSV: 성욱 님 채점표 형식 ----------
def test_export_desc_columns(tmp_path, monkeypatch):
    import export_preds

    n = 4
    data = pd.DataFrame(
        {
            "answer_id": [f"A{i}" for i in range(n)],
            "prompt_id": "P1",
            "grade": "초5",
            "text": "x",
        }
    )
    for it in baseline.ITEMS:
        data[f"{it}_r1"], data[f"{it}_r2"] = [1, 2, 3, 4], [2, 2, 3, 4]
    data_dir = tmp_path / "clean"
    data_dir.mkdir()
    data.to_csv(data_dir / "서술형_답안.csv", index=False)
    preds = tmp_path / "preds.npz"
    rng = np.random.default_rng(0)
    np.savez(
        preds,
        test=rng.random((n, len(baseline.ITEMS))),
        test_id=data["answer_id"].to_numpy(str),
    )
    monkeypatch.setattr(export_preds, "M2", tmp_path)  # 10/30 공유 CSV 비교는 건너뜀
    args = [
        "x",
        "--kind",
        "desc",
        "--preds",
        str(preds),
        "--name",
        "t",
        "--seed",
        "1",
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(tmp_path / "out"),
        "--date",
        "0101",
    ]
    monkeypatch.setattr("sys.argv", args)
    export_preds.main()
    out = pd.read_csv(tmp_path / "out" / "m2_서술_t_seed1_0101.csv")
    expect = ["answer_id", "prompt_id", "grade"] + [
        f"{it}_{s}" for it in baseline.ITEMS for s in ("r1", "r2", "pred")
    ]
    assert list(out.columns) == expect
    assert "text" not in out.columns  # 학생 글은 넣지 않음


# ---------- 세부 항목 11개 → 영역 3개 (train_545 --detail) ----------
def test_detail_to_areas_skips_unscored_items():
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    import train_545 as t

    monkeypatch_detail = t.USE_DETAIL
    t.USE_DETAIL = True
    try:
        df = pd.DataFrame({"essay_id": ["E1"]})
        for c in t.DETAIL:
            for r in (1, 2, 3):
                df[f"{c}_r{r}"] = 2.0
        for r in (1, 2, 3):  # 초등처럼 '문장 표현'(exp_2)을 채점 안 한 글
            df[f"exp_2_r{r}"] = np.nan
        y = t.train_target(df)
        assert np.isnan(y[0, t.DETAIL.index("exp_2")])
        pred = np.arange(len(t.DETAIL), dtype=float)[None, :]
        areas = t.to_areas(pred, df)
        exp_idx = [t.DETAIL.index(c) for c in ("exp_0", "exp_1")]  # exp_2는 빼고 평균
        assert areas[0, 2] == pytest.approx(pred[0, exp_idx].mean())
        org_idx = [t.DETAIL.index(f"org_{j}") for j in range(4)]
        assert areas[0, 0] == pytest.approx(pred[0, org_idx].mean())
    finally:
        t.USE_DETAIL = monkeypatch_detail


# ---------- 영역 3개 + 세부 11개 함께 (train_545 --both) ----------
def test_both_uses_first_three_as_areas():
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    import train_545 as t

    old = (t.USE_DETAIL, t.USE_BOTH)
    t.USE_DETAIL, t.USE_BOTH = True, True
    try:
        df = pd.DataFrame({"essay_id": ["E1"]})
        for c in t.AREAS + t.DETAIL:
            for r in (1, 2, 3):
                df[f"{c}_r{r}"] = float(r)  # 채점자 평균 = 2.0
        y = t.train_target(df)
        assert y.shape == (1, 3 + len(t.DETAIL))
        assert y[0, :3] == pytest.approx([2.0, 2.0, 2.0])
        pred = np.arange(3 + len(t.DETAIL), dtype=float)[None, :]
        assert t.to_areas(pred, df).tolist() == [[0.0, 1.0, 2.0]]
    finally:
        t.USE_DETAIL, t.USE_BOTH = old


# ---------- 표 만들기 (build_tables): 합성 JSON·zip으로 ----------
def _fake_json(answer_id="A1", item_name="내용 설명"):
    return {
        "essay_question": {"id": "P1", "subject": "국어", "grade": "초5", "prompt": "가짜"},
        "essay_answer": {"id": answer_id, "text": "가짜 글", "len_syllable": 4},
        "rubric": {"analytic": {"content_1": {"name": item_name}}},
        "score": {
            "personal": {
                "holistic": {"score": [3, 4]},
                "analytic": {"task_1": {"score": [2, 3]}, "content_1": {"score": [4, 4]}},
            }
        },
    }


def test_build_tables_to_row_and_type():
    import build_tables

    row = build_tables.to_row("train", _fake_json(item_name="주장의 타당성"), with_type=True)
    assert row["essay_type"] == "주장"
    assert (row["hol_r1"], row["hol_r2"]) == (3, 4)
    assert (row["task_1_r1"], row["task_1_r2"]) == (2, 3)  # _r1 = 전문가 1, _r2 = 전문가 2
    assert build_tables.essay_type_of("감정 표현") == "정서"
    assert build_tables.decode_name("#Uc11c#Uc220") == "서술"


def test_build_tables_reads_nested_zip_and_skips_other_json(tmp_path):
    import io
    import json
    import zipfile

    import build_tables

    def inner(items):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, obj in items:
                z.writestr(name, json.dumps(obj, ensure_ascii=False))
        return buf.getvalue()

    outer = tmp_path / "data.zip"
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr(
            "02.라벨링/TL_1.zip", inner([("a.json", _fake_json("A1")), ("x.json", {"q": 1})])
        )
        z.writestr("02.라벨링/VL_1.zip", inner([("b.json", _fake_json("B1"))]))
        z.writestr("01.원천/TS_1.zip", inner([("c.json", _fake_json("C1"))]))  # 라벨 zip 아님
    got = [(s, j["essay_answer"]["id"]) for s, j in build_tables.iter_label_json(outer)]
    assert sorted(got) == [("train", "A1"), ("valid", "B1")]


# ---------- 모델 입력 첫 문장 (train.first_segment): 서비스 입력 형식과 같아야 함 ----------
def test_first_segment_no_prompt_with_keyword():
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    import train

    df = pd.DataFrame({"grade": ["초5"], "prompt": ["지시문"], "keyword": ["가, 나"]})
    assert train.first_segment(df, with_keyword=True, no_prompt=True) == [
        "[학년] 초5 [핵심어] 가, 나"
    ]
    assert train.first_segment(df) == ["[학년] 초5 [지시문] 지시문"]
