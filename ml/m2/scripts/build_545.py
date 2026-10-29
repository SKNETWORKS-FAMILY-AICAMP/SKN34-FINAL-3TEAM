"""AI Hub 545 에세이 글 평가 데이터 → 학습용 표 data/에세이545_답안.csv.gz (커밋 금지: 데이터)

채점자 3명의 구성(org)·내용(cont)·표현(exp) 세부 점수(0~3)를 영역마다 평균해 채점자별 열로 저장한다.
실행: python scripts/build_545.py "<024.에세이 글 평가 데이터.zip 경로>"
"""

import csv, gzip, io, json, sys, zipfile
from pathlib import Path

M2 = Path(__file__).resolve().parents[1]
src = sys.argv[1]
z = zipfile.ZipFile(src)


def name(i):
    try:
        return i.filename.encode("cp437").decode("cp949")
    except Exception:
        return i.filename


cols = ["split", "essay_id", "grade", "essay_type", "subject", "text"] + [
    f"{a}_r{r}" for a in ("org", "cont", "exp") for r in (1, 2, 3)
]
out = M2 / "data" / "에세이545_답안.csv.gz"
n = 0
with gzip.open(out, "wt", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(cols)
    for i in z.infolist():
        nm = name(i)
        if not (nm.endswith(".zip") and "라벨링" in nm):
            continue
        sp = "TL" if "/1.Training/" in nm else "VL"
        iz = zipfile.ZipFile(io.BytesIO(z.read(i)))
        for f in iz.namelist():
            if not f.endswith(".json"):
                continue
            d = json.loads(iz.read(f).decode("utf-8-sig"))
            text = " ".join(p["paragraph_txt"] for p in d["paragraph"])
            det = d["score"]["essay_scoreT_detail"]
            g = d["student"]["student_grade"]  # 예: 초등_5학년
            grade = {"초등": "초", "중등": "중", "고등": "고"}[
                g.split("_")[0]
            ] + g.split("_")[1].rstrip("학년")
            # 학년군마다 채점하지 않는 세부 항목은 가중치 0 + 3명 모두 0점으로 들어 있음 (루브릭 설명서 표 5·6).
            # 그 항목을 빼고 평균한다 (10/29: 넣고 평균했더니 초4~중1 표현에 0이 섞여 초등 표현이 0.344로 낮았음).
            # 위치 대응은 VL에서 확인: 가중치 0인 글은 해당 위치가 예외 없이 3명 모두 0
            rub = d["rubric"]
            skip = {
                "org": {
                    1: rub["organization_weight"]["org_paragraph"],
                    2: rub["organization_weight"]["org_coherence"],
                },
                "cont": {2: rub["content_weight"]["con_prompt"]},
                "exp": {2: rub["expression_weight"]["exp_style"]},
            }
            sc = []
            for a in ("org", "cont", "exp"):
                for r in range(3):
                    v = det[f"essay_scoreT_{a}"][r]
                    used = [x for j, x in enumerate(v) if skip[a].get(j, 1) != 0]
                    sc.append(round(sum(used) / len(used), 4))
            w.writerow(
                [
                    sp,
                    d["info"]["essay_id"],
                    grade,
                    d["info"]["essay_type"],
                    d["info"]["essay_main_subject"],
                    text,
                ]
                + sc
            )
            n += 1
print(f"저장 {out.name}: {n:,}건, {out.stat().st_size / 1e6:.1f}MB")
