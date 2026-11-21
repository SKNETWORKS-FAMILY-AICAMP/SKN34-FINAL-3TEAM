"""memory@1 정답 확인 도우미 (README "정답 확인"). 표준 라이브러리만 쓴다.

정답을 가린 채 학생별 기록을 보고 질문마다 정답 회차(W1~W6)를 직접 고른 뒤, 원래 정답(gold)과 맞춰 본다.
    python -I evaluation/datasets/memory/answer_check.py page --split eval
      → evaluation/results/memory/answer-check__eval.html (브라우저로 열기, 학생 답 있음 → 커밋·공유 안 함, 정답은 넣지 않음)
    (화면에서 고른 뒤 '결과 복사' → 파일로 저장)
    python -I evaluation/datasets/memory/answer_check.py compare --answers <복사한 결과 JSON 파일>
      → 다른 것만 출력. 확인 끝나면 --apply 수빈 을 붙여 일치한 질문의 checkedBy에 이름을 넣음
memory@2(#853)는 두 명령 앞에 --dataset evaluation/datasets/memory@2 (기준일·기간 규칙을 화면 위에 보여 줌,
결과 파일 이름 answer-check__memory@2__eval.html)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "evaluation" / "results" / "memory"
DAYS = {"MON": "월", "TUE": "화", "WED": "수", "THU": "목", "FRI": "금"}
DATASET = HERE  # main에서 --dataset으로 바꿈
NOTE_V1 = ("검색 대상은 W1~W6(다 푼 회차)뿐이에요. 회색 카드는 범위 밖이라, 그 기록에만 맞는 질문은 <b>없음</b>이에요.")
NOTE_V2 = ("오늘은 <b>{today}</b>이라고 생각하고 고르세요(이번 주 기록은 검색 대상 아님). 질문이 말하는 기간에 "
           "<b>월~금 중 3일 이상</b> 든 주만 정답이에요. 1~2일만 걸친 주(예: '10월'에 9/28 주)는 정답이 아니에요. "
           "소재가 있는 질문은 그 소재가 나온 주만, 맞는 주가 없으면 <b>없음</b>.")


def load():
    students = json.loads((DATASET / "students.json").read_text(encoding="utf-8"))
    themes = {t["themeKey"]: t for t in json.loads((DATASET / "themes.json").read_text(encoding="utf-8"))}
    lines = (DATASET / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    return students, themes, lines


def rounds_of(data, st):
    """memory@1은 students.json rounds, memory@2는 최근 weekCount주(주별 미션 답 변형)."""
    if "rounds" in st:
        return st["rounds"]
    return [{"week": wk, "themeKey": f"T{wk[1:]}", "complete": True,
             "answers": {d: data["weekMissions"][wk][d]["answers"][st["variant"]] for d in DAYS}}
            for wk in list(data["weeks"])[-st["weekCount"]:]]


def answer_parts(a):
    if a is None:
        return None
    if "text" in a:
        return [a["text"]]
    if "essay" in a:
        e = a["essay"]
        return [f"주장: {e['claim']}", f"까닭1: {e['reasons'][0]}", f"까닭2: {e['reasons'][1]}", f"반대에 답하기: {e['rebuttal']}"]
    if "steps" in a:
        return ["풀이: " + " / ".join(a["steps"]), f"최종 답: {a.get('finalAnswer', '')}"]
    return [json.dumps(a, ensure_ascii=False)]


def cmd_page(args):
    data, themes, lines = load()
    queries = [json.loads(x) for x in lines if x.strip()]
    pages = []
    for st in data["students"]:
        if st["split"] != args.split:
            continue
        rounds, labels = [], {}
        for rd in rounds_of(data, st):
            th = themes[rd["themeKey"]]
            answers = [{"day": DAYS[d], "parts": answer_parts(a)} for d, a in rd["answers"].items() if a is not None]
            start = data["weeks"].get(rd["week"], "")
            if "weekMissions" in data:  # memory@2: 고르는 단추에 날짜, 카드에 월~금 날짜
                day0 = dt.date.fromisoformat(start)
                labels[rd["week"]] = f"{day0.month}/{day0.day}"
                start = f"{start} (월) ~ {(day0 + dt.timedelta(days=4)).isoformat()} (금)"
            rounds.append({"week": rd["week"], "date": start, "title": th["title"],
                           "story": [line["text"] for day in th["days"] for line in day["dialogue"]],
                           "answers": answers, "outside": None if rd["complete"] else "3문제만 풀고 액자 없음"})
        if st.get("extra"):
            rounds.append({"week": "추가 문제", "date": "", "title": "", "story": [], "outside": "추가 문제(EXTRA)",
                           "answers": [{"day": DAYS.get(st["extra"].get("missionDay"), ""), "parts": answer_parts(st["extra"]["answer"])}]})
        if st.get("current"):
            rounds.append({"week": "이번 주", "date": "", "title": "", "story": [], "outside": "진행 중인 주",
                           "answers": [{"day": "", "parts": answer_parts(st["current"]["answer"])}]})
        qs = [{"id": q["queryId"], "q": q["query"]} for q in queries if q["studentKey"] == st["studentKey"]]
        pages.append({"key": st["studentKey"], "grade": st["grade"], "rounds": rounds, "questions": qs, "labels": labels})
    v2 = data["dataset"] != "memory@1"
    note = NOTE_V2.format(today=html.escape(data.get("evalToday", ""))) if v2 else NOTE_V1
    split = f"{data['dataset']}__{args.split}" if v2 else args.split  # 저장 이름·브라우저 저장 칸을 memory@1과 나눔
    payload = json.dumps({"split": split, "note": note, "students": pages}, ensure_ascii=False).replace("</", "<\\/")
    out = pathlib.Path(args.out or OUT / f"answer-check__{split}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PAGE.replace("__DATA__", payload).replace("__SPLIT__", html.escape(split)), encoding="utf-8")
    print(f"{args.split} 학생 {len(pages)}명 · 질문 {sum(len(p['questions']) for p in pages)}개 → {out}")


def cmd_compare(args):
    _, _, lines = load()
    queries = {json.loads(x)["queryId"]: json.loads(x) for x in lines if x.strip()}
    mine = json.loads(pathlib.Path(args.answers).read_text(encoding="utf-8-sig"))["answers"]
    same, diff, empty = [], [], []
    for qid, v in sorted(mine.items()):
        if not v.get("pick"):
            empty.append(qid)
            continue
        got = set() if v["pick"] == ["없음"] else set(v["pick"])
        gold = {g["week"] for g in queries[qid]["gold"]}
        (same if got == gold else diff).append((qid, got, gold, v.get("memo", "")))
    print(f"맞춰 본 질문 {len(same) + len(diff)}개 · 같음 {len(same)} · 다름 {len(diff)} · 빈칸 {len(empty)} {empty if empty else ''}")
    for qid, got, gold, memo in diff:
        q = queries[qid]
        print(f"  {qid} {q['category']:10} {q['query']} | 내 답 {sorted(got) or '없음'} | 원래 정답 {sorted(gold) or '없음'} | 근거 {q.get('evidence', '')}"
              + (f" | 메모 {memo}" if memo else ""))
    memos = [(qid, v["memo"]) for qid, v in sorted(mine.items()) if v.get("memo") and qid in {s[0] for s in same}]
    for qid, memo in memos:
        print(f"  (같지만 메모) {qid} {queries[qid]['query']} | {memo}")
    if args.apply:
        ok = {s[0] for s in same}
        out = []
        for x in lines:
            if not x.strip():
                out.append(x)
                continue
            q = json.loads(x)
            if q["queryId"] in ok and args.apply not in q["checkedBy"]:
                q["checkedBy"].append(args.apply)
            out.append(json.dumps(q, ensure_ascii=False))
        (DATASET / "queries.jsonl").write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"checkedBy에 '{args.apply}' 넣음: 같은 {len(ok)}개 (다른 것은 고친 뒤 다시 compare)")


PAGE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>정답 확인 __SPLIT__</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:"Pretendard","Malgun Gothic",system-ui,sans-serif;color:#1d2433;background:#f5f6f8;font-size:15px;line-height:1.55}
header{position:sticky;top:0;z-index:5;background:#1f3a5f;color:#fff;padding:10px 18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
header b{margin-right:8px}.tab{border:1px solid #9fb3cf;background:transparent;color:#fff;border-radius:6px;padding:4px 12px;cursor:pointer;font-size:14px}
.tab.on{background:#fff;color:#1f3a5f;font-weight:700}.prog{margin-left:auto;font-size:14px}
main{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(360px,1fr);gap:16px;padding:16px 18px}
.card{background:#fff;border:1px solid #dde2ea;border-radius:10px;padding:12px 14px;margin-bottom:12px}
.card.out{background:#eef0f3;border-style:dashed;color:#555}
.wk{font-weight:700;font-size:16px}.wk small{font-weight:400;color:#667;margin-left:6px}.title{font-size:17px;font-weight:700;color:#1f3a5f;margin:2px 0 6px}
.badge{display:inline-block;background:#888;color:#fff;border-radius:4px;font-size:12px;padding:1px 6px;margin-left:6px}
details{margin:4px 0 8px;color:#556}summary{cursor:pointer;font-size:13px}
.ans{display:grid;grid-template-columns:28px 1fr;gap:4px 8px;margin-top:4px}.day{font-weight:700;color:#1f3a5f}
.side{position:sticky;top:58px;align-self:start;max-height:calc(100vh - 74px);overflow:auto}
.q{background:#fff;border:1px solid #dde2ea;border-radius:10px;padding:10px 12px;margin-bottom:8px}
.q.done{border-color:#7fb08a;background:#f3faf4}.qid{color:#889;font-size:12px}.qt{font-weight:600;margin:2px 0 6px}
.pick{border:1px solid #c5ccd8;background:#fff;border-radius:6px;padding:3px 9px;margin:2px 2px 2px 0;cursor:pointer;font-size:14px}
.pick.on{background:#1f3a5f;color:#fff;border-color:#1f3a5f}.pick.none.on{background:#b54848;border-color:#b54848}
.memo{width:100%;margin-top:6px;border:1px solid #d5dbe5;border-radius:6px;padding:4px 8px;font:inherit;font-size:13px}
.bar{display:flex;gap:8px;margin:6px 0 12px}.bar button{border:0;background:#1f3a5f;color:#fff;border-radius:6px;padding:8px 14px;cursor:pointer;font-size:14px}
.bar button.sub{background:#8a94a6}.msg{font-size:13px;color:#2e7d32;min-height:18px}
mark{background:#ffe58a}
</style></head><body>
<header><b>정답 확인 (__SPLIT__)</b><span id="tabs"></span><span class="prog" id="prog"></span></header>
<main><section id="left"></section><aside class="side" id="right"></aside></main>
<script>
const DATA = __DATA__;
const KEY = "memory-answer-check-" + DATA.split;
let state = {}; try { state = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
let cur = DATA.students[0].key;
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
function weeks(st) { return st.rounds.filter(r => !r.outside).map(r => r.week); }
function render() {
  const st = DATA.students.find(s => s.key === cur);
  document.getElementById("tabs").innerHTML = DATA.students.map(s => {
    const n = s.questions.filter(q => (state[q.id]||{}).pick && state[q.id].pick.length).length;
    return `<button class="tab ${s.key===cur?"on":""}" data-k="${s.key}">${s.key} (${n}/${s.questions.length})</button>`; }).join(" ");
  const all = DATA.students.flatMap(s => s.questions), done = all.filter(q => (state[q.id]||{}).pick && state[q.id].pick.length).length;
  document.getElementById("prog").textContent = `전체 ${done}/${all.length}`;
  document.getElementById("left").innerHTML = `<div class="card"><b>${st.key} (초${st.grade}) 기록</b> — ${DATA.note}</div>` +
    st.rounds.map(r => `<div class="card ${r.outside?"out":""}">
      <div class="wk">${esc(r.week)}<small>${esc(r.date)}</small>${r.outside?`<span class="badge">범위 밖 · ${esc(r.outside)}</span>`:""}</div>
      ${r.title?`<div class="title">${esc(r.title)}</div>`:""}
      ${r.story.length?`<details><summary>이야기 대사 보기</summary>${r.story.map(esc).join("<br>")}</details>`:""}
      <div class="ans">${r.answers.map(a => `<div class="day">${esc(a.day)}</div><div>${a.parts.map(esc).join("<br>")}</div>`).join("")}</div>
    </div>`).join("");
  const ws = weeks(st);
  document.getElementById("right").innerHTML = `<div class="bar"><button id="copy">결과 복사</button><button class="sub" id="dl">결과 파일 저장</button></div><div class="msg" id="msg"></div>` +
    st.questions.map(q => { const s = state[q.id] || {pick: [], memo: ""};
      return `<div class="q ${s.pick&&s.pick.length?"done":""}" data-q="${q.id}"><div class="qid">${q.id}</div><div class="qt">${esc(q.q)}</div>
      ${ws.map(w => `<button class="pick ${s.pick.includes(w)?"on":""}" data-w="${w}">${(st.labels||{})[w]||w}</button>`).join("")}<button class="pick none ${s.pick.includes("없음")?"on":""}" data-w="없음">없음</button>
      <input class="memo" placeholder="메모(애매하면 이유)" value="${esc(s.memo||"")}"></div>`; }).join("");
}
document.addEventListener("click", e => {
  const t = e.target;
  if (t.classList.contains("tab")) { cur = t.dataset.k; render(); window.scrollTo(0, 0); return; }
  if (t.classList.contains("pick")) {
    const id = t.closest(".q").dataset.q, w = t.dataset.w, s = state[id] || (state[id] = {pick: [], memo: ""});
    if (w === "없음") s.pick = s.pick.includes("없음") ? [] : ["없음"];
    else { s.pick = s.pick.filter(x => x !== "없음"); s.pick = s.pick.includes(w) ? s.pick.filter(x => x !== w) : [...s.pick, w].sort(); }
    save(); render(); return; }
  if (t.id === "copy" || t.id === "dl") {
    const answers = {}; DATA.students.forEach(st => st.questions.forEach(q => { const s = state[q.id] || {}; answers[q.id] = {pick: s.pick || [], memo: s.memo || ""}; }));
    const text = JSON.stringify({split: DATA.split, answers}, null, 0);
    if (t.id === "copy") navigator.clipboard.writeText(text).then(() => { document.getElementById("msg").textContent = "복사했어요. 채팅에 붙여 주세요."; }, () => { document.getElementById("msg").textContent = "복사가 막혔어요. '결과 파일 저장'을 써 주세요."; });
    else { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], {type: "application/json"})); a.download = `answer-check__${DATA.split}__mine.json`; a.click(); document.getElementById("msg").textContent = "다운로드 폴더에 저장했어요."; }
  }
});
document.addEventListener("input", e => { if (e.target.classList.contains("memo")) { const id = e.target.closest(".q").dataset.q; (state[id] || (state[id] = {pick: [], memo: ""})).memo = e.target.value; save(); } });
render();
</script></body></html>"""


def main():
    global DATASET
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(HERE), help="평가셋 폴더(기본 memory@1, memory@2는 evaluation/datasets/memory@2)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("page")
    p.add_argument("--split", choices=["eval", "tune", "deleted"], default="eval")
    p.add_argument("--out")
    p = sub.add_parser("compare")
    p.add_argument("--answers", required=True, help="화면에서 복사·저장한 결과 JSON 파일")
    p.add_argument("--apply", help="일치한 질문 checkedBy에 넣을 이름(확인 끝난 뒤에만)")
    args = ap.parse_args()
    DATASET = pathlib.Path(args.dataset).resolve()
    {"page": cmd_page, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
