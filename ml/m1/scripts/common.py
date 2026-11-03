"""M1 스크립트 공용: 경로, 71716 읽기, 레코드 만들기.

71716 실제 구조 (Validation 초5·Training 초5에서 확인, 2026-10-22)
- AI Hub에서 받은 그대로 zip 묶음. 풀어 놓을 필요 없이 zip을 바로 읽는다.
- 필요한 것은 '손글씨풀이 라벨링' zip뿐:
  Training/02.라벨링데이터/TL_3.*.zip, Validation/02.라벨링데이터/VL_3.*.zip
  (TS_3·VS_3 원천 zip은 손글씨 이미지라 1~2GB씩이고 M1에는 쓰지 않는다)
- zip 안: 풀이 1건 = JSON 1개 (UTF-8 BOM). 파일명 끝 _O/_X 가 정답/오답과 일치.
- 한 파일에 문제(OCR_info) · 모범답안(answer_info) · 학생 풀이(explanation_info) 가 같이 들어 있다.
- 텍스트는 손글씨 OCR LaTeX → mathtext.latex_to_text 로 평문화.
- id = "그룹_문항" (예: 26621_87487). 같은 그룹은 숫자·이름만 바꾼 쌍둥이 문항이고,
  AI Hub의 Training/Validation은 문항은 다르지만 그룹은 겹친다 → 그룹 단위로 다시 나눈다.

라벨 정의 (AI Hub 데이터 페이지)
- explanation_correct: 0 정답 / 1 오답
- explanation_error_required: 필수 과정 실수 개수 (0~99)
- explanation_error_clac_acc: 0 실수 없음 / 0.5 답은 맞지만 계산과정 안 씀 / 1 실수 있음
- explanation_error_clac_num: 계산 원리 실수 개수
- answer_required_num: 모범답안의 필수 과정 점수
"""

import json
import os
import zipfile
from pathlib import Path

from mathtext import latex_to_text, model_input  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent  # ml/m1

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# 받은 폴더를 그대로 가리키면 된다: .env 또는 명령줄 인자로 바꿀 수 있음
RAW_DIR = Path(os.getenv("AIHUB_71716_DIR", str(ROOT / "data" / "71716")))
WORK_DIR = ROOT / "work"  # (커밋 안 함) 가공본 records.csv
REPORT_DIR = ROOT / "results"  # 평가 결과 eval_m1.md (원문 없음)
# EDA 리포트는 AI Hub 풀이 원문 예시를 담으므로 커밋하지 않는 폴더에 씀 (NFR-DAT-03, #263)
EDA_REPORT_DIR = WORK_DIR / "reports"
MODEL_DIR = ROOT / "models"  # (커밋 안 함) 학습한 가중치

LABEL_ZIP_PREFIXES = ("TL_3", "VL_3")  # 손글씨풀이 라벨링 zip만
GRADE_NAMES = {
    "P3": "초3",
    "P4": "초4",
    "P5": "초5",
    "P6": "초6",
    "M1": "중1",
    "M2": "중2",
    "M3": "중3",
    "H": "고(공통수학)",
}


def _split_hint(name):
    n = str(name)
    if "TL_" in n or "Training" in n:
        return "Training"
    if "VL_" in n or "Validation" in n:
        return "Validation"
    return ""


def sources(root=RAW_DIR):
    """읽을 대상: 손글씨풀이 라벨링 zip + (풀어 둔 경우) 그 안의 JSON 폴더."""
    root = Path(root)
    zips = sorted(p for p in root.rglob("*.zip") if p.name.startswith(LABEL_ZIP_PREFIXES))
    loose = sorted(p for p in root.rglob("*.json") if p.is_file())
    return zips, loose


def iter_items(root=RAW_DIR):
    """(출처 이름, AI Hub 분할, JSON 객체) 를 하나씩. 읽기 실패는 (이름, 분할, Exception)."""
    zips, loose = sources(root)
    for zp in zips:
        hint = _split_hint(zp.name)
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():
                if not n.lower().endswith(".json"):
                    continue
                try:
                    yield (
                        f"{zp.name}:{n.strip('/')}",
                        hint,
                        json.loads(z.read(n).decode("utf-8-sig")),
                    )
                except Exception as e:  # noqa: BLE001
                    yield f"{zp.name}:{n}", hint, e
    for p in loose:
        try:
            with open(p, encoding="utf-8-sig") as f:
                yield p.name, _split_hint(p.as_posix()), json.load(f)
        except Exception as e:  # noqa: BLE001
            yield p.name, _split_hint(p.as_posix()), e


def _first(lst):
    return lst[0] if isinstance(lst, list) and lst and isinstance(lst[0], dict) else {}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_record(obj, source="", aihub_split=""):
    """71716 JSON 1개 → 평평한 레코드. 풀이가 없거나 정답 라벨이 없으면 None."""
    if not isinstance(obj, dict) or "explanation_info" not in obj:
        return None
    qi, ocr, ans, ex = (
        _first(obj.get(k)) for k in ("question_info", "OCR_info", "answer_info", "explanation_info")
    )
    solution = ex.get("explanation_text") or ""
    correct = _num(ex.get("explanation_correct"))
    if not str(solution).strip() or correct is None:
        return None
    qid = str(obj.get("id") or obj.get("question_filename") or source)
    final = next(
        (
            b.get("text")
            for b in ans.get("answer_bbox") or []
            if isinstance(b, dict) and b.get("type") == "answer" and b.get("text")
        ),
        "",
    )
    req = _num(ex.get("explanation_error_required"))
    calc = _num(ex.get("explanation_error_clac_acc"))
    name = Path(source.split(":")[-1]).stem
    return {
        "question_id": qid,
        "group_id": qid.split("_")[0],
        "grade": str(qi.get("question_grade") or ""),
        "unit": str(qi.get("question_unit") or ""),
        "topic_name": str(qi.get("question_topic_name") or ""),
        "question": ocr.get("question_text") or "",
        "reference_answer": final or "",
        "solution": solution,
        "is_correct": int(correct == 0),  # 0 = 정답
        "required_errors": "" if req is None else int(req),
        "required_num": ans.get("answer_required_num", ""),
        "has_required_error": "" if req is None else int(req > 0),
        "calc_accuracy": "" if calc is None else str(calc),  # "0.0" / "0.5" / "1.0" 를 합치지 않음
        "calc_principle_errors": ex.get("explanation_error_clac_num", ""),
        "difficulty": ex.get("explanation_difficulty", ""),
        "filename_ox": name.rsplit("_", 1)[-1] if name.endswith(("_O", "_X")) else "",
        "aihub_split": aihub_split,
        "source": source,
    }
