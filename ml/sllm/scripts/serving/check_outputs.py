"""벤치 결과 JSON의 생성 원문을 ai-service 규칙(checks.py)으로 검사한다. 원문은 출력하지 않고 통과 여부만 센다."""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app.report_explanation import checks
from app.report_explanation.models import ExplanationDetail
from app.report_narrative.prompts import GeneratedNarrative
P = json.load(open(sys.argv[2], encoding="utf-8")); src = P["explanation_text"]
for f in sys.argv[3:]:
    d = json.load(open(f, encoding="utf-8")); rows = d["single"]
    out = {"file": Path(f).name, "explanation": [], "narrative": []}
    for r in rows:
        try:
            if r["kind"] == "explanation":
                det = ExplanationDetail.model_validate_json(r["text"])
                sec = checks.parts(det, src)
                ok = bool(sec) and sec[0][0] == "상세 분석" and all(checks.allowed(b, src) for _, b in sec)
                out["explanation"].append({"json": True, "pass": ok, "sections": len(sec), "chars": len(checks.compose(sec)) if sec else 0})
            else:
                n = GeneratedNarrative.model_validate_json(r["text"])
                out["narrative"].append({"json": True, "narrative_chars": len(n.narrative), "question": bool(n.evening_question.strip()), "quotes": len(n.cited_quotes)})
        except Exception as e:
            out[r["kind"]].append({"json": False, "error": type(e).__name__})
    print(json.dumps(out, ensure_ascii=False))
