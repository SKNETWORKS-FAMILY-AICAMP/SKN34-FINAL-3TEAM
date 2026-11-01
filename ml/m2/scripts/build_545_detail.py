"""545 세부 항목 11개 점수표 → data/clean/에세이545_세부.csv.gz (학생 글 없음, 커밋 금지: 데이터)

열: essay_id + 세부 항목 11개 × 채점자 3명 (org_0~3, cont_0~3, exp_0~2 _r1~r3), 0~3점
학년군마다 채점하지 않는 항목(가중치 0, 3명 모두 0점)은 빈칸(NaN) → 학습에서 빠짐
위치 의미(루브릭 설명서·10/29 VL 확인): org [0]문단 간 [1]문단 내 [2]일관성 [3]분량 /
cont [2]프롬프트 독해력(논술형만), 나머지는 주제 명료성·설명 구체성·창의성 / exp [2]문장 표현
영역 점수는 build_545.py v2와 같은 방식(빈칸 빼고 평균)으로 이 표에서 다시 만들 수 있음
실행: python scripts/build_545_detail.py "<024.에세이 글 평가 데이터.zip 경로>"
"""

import csv
import gzip
import io
import json
import sys
import zipfile
from pathlib import Path

M2 = Path(__file__).resolve().parents[1]
N = {"org": 4, "cont": 4, "exp": 3}
z = zipfile.ZipFile(sys.argv[1])


def name(i):
    try:
        return i.filename.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):  # UTF-8 이름은 그대로
        return i.filename


cols = ["essay_id"] + [f"{a}_{j}_r{r}" for a in N for j in range(N[a]) for r in (1, 2, 3)]
out = M2 / "data" / "clean" / "에세이545_세부.csv.gz"
n = 0
with gzip.open(out, "wt", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(cols)
    for i in z.infolist():
        nm = name(i)
        if not (nm.endswith(".zip") and "라벨링" in nm):
            continue
        iz = zipfile.ZipFile(io.BytesIO(z.read(i)))
        for f in iz.namelist():
            if not f.endswith(".json"):
                continue
            d = json.loads(iz.read(f).decode("utf-8-sig"))
            det, rub = d["score"]["essay_scoreT_detail"], d["rubric"]
            skip = {
                ("org", 1): rub["organization_weight"]["org_paragraph"],
                ("org", 2): rub["organization_weight"]["org_coherence"],
                ("cont", 2): rub["content_weight"]["con_prompt"],
                ("exp", 2): rub["expression_weight"]["exp_style"],
            }
            row = [d["info"]["essay_id"]]
            for a, n_items in N.items():
                for j in range(n_items):
                    for r in range(3):
                        row.append(
                            "" if skip.get((a, j), 1) == 0 else det[f"essay_scoreT_{a}"][r][j]
                        )
            w.writerow(row)
            n += 1
print(f"저장 {out.name}: {n:,}건, {out.stat().st_size / 1e6:.1f}MB")
