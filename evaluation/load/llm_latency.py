"""실제 LLM 조건 응답 시간 실측 (#630, NFR-PRF-01). 동시 사용자 1명, core 공개·관리자 API 경로.

화면과 같은 경로로 한 건씩 보내고 요청 시작부터 SSE `done`(또는 작업 완료 상태)까지의 시간을 잰다.
결과는 저장소 밖 JSONL에 한 줄씩 쌓고 `summary`가 종류별 건수·p50·p95·최대를 낸다. 같은 시간대의
ai `llm_usage`(LLM 호출 1회 지연·토큰·비용)는 `llm_usage_window.sql`로 따로 본다.

    python evaluation/load/llm_latency.py judge   --secrets <밖>/secrets.json --out <밖>/samples.jsonl --judgments 20 --followups 20
    python evaluation/load/llm_latency.py analyze --secrets <밖>/secrets.json --out <밖>/samples.jsonl --count 20
    python evaluation/load/llm_latency.py memory  --secrets <밖>/secrets.json --out <밖>/samples.jsonl --per-child 3
    python evaluation/load/llm_latency.py report  --admin-env <밖>/admin.env --out <밖>/samples.jsonl --report-id <리포트 ID> --count 5
    python evaluation/load/llm_latency.py theme   --admin-env <밖>/admin.env --out <밖>/samples.jsonl --week-start 2027-01-04 --discard
    python evaluation/load/llm_latency.py summary --out <밖>/samples.jsonl

환경 변수: LOAD_API_BASE(기본 http://127.0.0.1/api/v1), LOAD_API_HOST(kind: api.sagomungchi.local),
LOAD_ORIGIN(기본 http://localhost:5173). 비밀 파일은 prepare_accounts.py 형식이다.
토큰·비밀번호·PIN·답변 원문·AI 응답 원문은 출력하지도 저장하지도 않는다. 상태·건수·시간만 남긴다.
"""
import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KST = dt.timezone(dt.timedelta(hours=9))

# 자체 작성한 가상 답변. 첫 답은 이유를 빼 되묻기가 나오기 쉽게, 되묻기 답은 이유·예시를 더한다.
FIRST = [
    "나는 그렇게 생각해.",
    "친구랑 같이 하면 좋아.",
    "나는 그게 맞는 것 같아.",
    "차례를 지키는 게 좋아.",
    "나는 반대야.",
]
SECOND = [
    "왜냐하면 함께 하면 서로 도울 수 있기 때문이야. 지난번에 친구와 같이 정리했더니 금방 끝났어.",
    "모두가 기분 좋게 지낼 수 있기 때문이야. 예를 들어 순서를 정하면 다투지 않아.",
    "직접 해 보니 더 잘 알게 됐기 때문이야. 그래서 다음에도 그렇게 하고 싶어.",
]
QUESTIONS = [
    "이번 주에 되묻기를 받고 생각을 더 쓴 적이 몇 번이야?",
    "지난주보다 답을 끝까지 쓴 날이 늘었어?",
    "어떤 생각 유형 미션을 가장 많이 했어?",
    "이유를 쓰는 습관은 어떻게 변하고 있어?",
    "가장 오래 걸린 미션은 뭐였어?",
]


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Api:
    def __init__(self):
        self.base = os.environ.get("LOAD_API_BASE", "http://127.0.0.1/api/v1").rstrip("/")
        self.host = os.environ.get("LOAD_API_HOST", "api.sagomungchi.local")
        self.origin = os.environ.get("LOAD_ORIGIN", "http://localhost:5173")

    def request(self, method, path, body=None, token=None, cookie=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if self.host:
            req.add_header("Host", self.host)
        req.add_header("Origin", self.origin)
        req.add_header("X-Requested-With", "XMLHttpRequest")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        if cookie:
            req.add_header("Cookie", cookie)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        return req

    def call(self, method, path, body=None, token=None, cookie=None, headers=None, timeout=120):
        try:
            with urllib.request.urlopen(self.request(method, path, body, token, cookie, headers), timeout=timeout) as r:
                raw, status = r.read(), r.status
        except urllib.error.HTTPError as e:
            raw, status = e.read(), e.code
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, None

    def ok(self, label, status, payload, allowed=(200, 201)):
        if status not in allowed:
            code = payload.get("code") if isinstance(payload, dict) else ""
            raise SystemExit(f"{label} 실패: HTTP {status} {code}")
        return payload

    def sse(self, path, token, body=None, timeout=200):
        """SSE를 끝까지 읽는다. 시작·첫 이벤트·done까지의 시간(ms)과 이벤트별 JSON을 돌려준다(원문은 저장하지 않음)."""
        start = time.perf_counter()
        first = None
        events = []
        status = 0
        try:
            req = self.request("POST", path, body, token, headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status = r.status
                name, data = None, []
                for raw in r:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        name = line[6:].strip()
                    elif line.startswith("data:"):
                        data.append(line[5:].lstrip())
                    elif line == "" and name:
                        if first is None:
                            first = (time.perf_counter() - start) * 1000
                        try:
                            parsed = json.loads("\n".join(data)) if data else None
                        except ValueError:
                            parsed = None
                        events.append((name, parsed))
                        if name == "done":
                            break
                        name, data = None, []
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                events.append(("http_error", json.loads(e.read() or b"{}")))
            except ValueError:
                events.append(("http_error", None))
        except (TimeoutError, urllib.error.URLError) as e:
            events.append(("transport_error", {"error": type(e).__name__}))
        total = (time.perf_counter() - start) * 1000
        return {"status": status, "ms": round(total), "firstEventMs": None if first is None else round(first), "events": events}


def load_account(path):
    secrets_path = Path(path)
    resolved = secrets_path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise SystemExit("--secrets는 저장소 밖이어야 합니다.")
    return json.loads(secrets_path.read_text(encoding="utf-8"))["accounts"][0]


def parent_token(api, account):
    s, p = api.call("POST", "/auth/parent/login", {"loginId": account["loginId"], "password": account["password"]})
    return api.ok("학부모 로그인", s, p, (200,))["accessToken"]


def student_token(api, account, child):
    s, p = api.call("POST", "/auth/student/login", {"childId": child["childId"], "pin": child["pin"]},
                    cookie="student_device=" + account["deviceCookie"])
    return api.ok("학생 로그인", s, p, (200,))["accessToken"]


class TokenSession:
    """학생·학부모 access는 15분이면 만료되고 refresh를 쓰지 않는다. 401이면 같은 자격 증명으로 다시 로그인한다."""

    def __init__(self, api, login):
        self.api, self.login = api, login
        self.token = login()

    def call(self, method, path, body=None, headers=None):
        s, p = self.api.call(method, path, body, token=self.token, headers=headers)
        if s == 401:
            self.token = self.login()
            s, p = self.api.call(method, path, body, token=self.token, headers=headers)
        return s, p

    def sse(self, path, body=None):
        result = self.api.sse(path, self.token, body)
        if result["status"] == 401:
            self.token = self.login()
            result = self.api.sse(path, self.token, body)
        return result


def write(out, row):
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def event(result, name):
    return next((data for n, data in result["events"] if n == name), None)


def judge(args):
    """미션마다 시도 시작 → 짧은 첫 답 → 판정 SSE → 되묻기가 오면 답 → 판정 SSE … → 마무리·돌아보기."""
    api = Api()
    account = load_account(args.secrets)
    judgments = followups = 0
    for index, child in enumerate(account["children"]):
        session = TokenSession(api, lambda child=child: student_token(api, account, child))
        # 분석 대화·주간 리포트 서술은 학생이 보호자 공유를 켜야 기록을 쓴다(학생 설정 화면과 같은 API)
        s, shared = session.call("PUT", "/students/me/sharing-preferences", {"parentSharingEnabled": True})
        api.ok("보호자 공유 켜기", s, shared, (200,))
        s, listed = session.call("GET", "/missions")
        missions = [m for m in api.ok("미션 목록", s, listed, (200,)).get("items", []) if m.get("inputType") in args.input_types]
        for mission in missions:
            if judgments >= args.judgments and followups >= args.followups:
                return report_counts(judgments, followups)
            mission_id = mission.get("missionId") or mission.get("id")
            s, attempt = session.call("POST", f"/missions/{mission_id}/attempts", {})
            if s not in (200, 201) or (attempt or {}).get("answers"):
                print(f"child{index} mission skip: HTTP {s} {(attempt or {}).get('code', '') if isinstance(attempt, dict) else ''}")
                continue
            followup_id = None
            for turn in range(args.max_turns):
                text = FIRST[(judgments + turn) % len(FIRST)] if turn == 0 else SECOND[(judgments + turn) % len(SECOND)]
                body = {"inputType": "NARRATIVE", "text": text, "dictatedByGuardian": False}
                if followup_id:
                    body["followupId"] = followup_id
                s, answer = session.call("POST", f"/attempts/{attempt['attemptId']}/answers", body,
                                         headers={"Idempotency-Key": str(uuid.uuid4())})
                if s != 201:
                    print(f"child{index} answer turn{turn}: HTTP {s} {(answer or {}).get('code', '') if isinstance(answer, dict) else ''}")
                    break
                started = now_iso()
                result = session.sse(f"/answers/{answer['answerId']}/feedback")
                done = event(result, "result") or {}
                judgment = done.get("judgment") or {}
                followup = done.get("followup") or {}
                judgments += 1
                if followup.get("source") in ("LLM", "LLM_RETRY"):
                    followups += 1
                write(args.out, {
                    "kind": "feedback", "startedAt": started, "endedAt": now_iso(), "ms": result["ms"],
                    "firstEventMs": result["firstEventMs"], "httpStatus": result["status"], "turn": turn,
                    "events": [n for n, _ in result["events"]], "feedbackStatus": done.get("status"),
                    "result": judgment.get("result"), "heldReason": judgment.get("heldReason"),
                    "m2": bool(judgment.get("modelScores")), "followupSource": followup.get("source"),
                    "followupType": followup.get("type"), "nextActions": done.get("nextActions"),
                    "error": (event(result, "error") or event(result, "http_error") or event(result, "transport_error") or {}).get("code")
                        or (event(result, "transport_error") or {}).get("error"),
                })
                print(f"feedback #{judgments} turn{turn} {result['ms']}ms {judgment.get('result')} followup={followup.get('source')}", flush=True)
                if "ANSWER_FOLLOWUP" not in (done.get("nextActions") or []):
                    break
                followup_id = followup.get("followupId")
            session.call("POST", f"/attempts/{attempt['attemptId']}/finish", {})
            session.call("POST", f"/attempts/{attempt['attemptId']}/reflection", {"difficulty": "NORMAL"})
    return report_counts(judgments, followups)


def report_counts(judgments, followups):
    print(f"판정 SSE {judgments}건, LLM 되묻기 {followups}건")
    return 0


def analyze(args):
    """프리미엄 자녀로 대화 하나를 만들고 질문 SSE를 count번 보낸다(동시 1명, 질문 사이 args.pause초)."""
    api = Api()
    account = load_account(args.secrets)
    session = TokenSession(api, lambda: parent_token(api, account))
    child = account["children"][args.child]
    today = dt.datetime.now(KST).date()
    s, created = session.call("POST", "/conversations", {"childId": child["childId"], "from": str(today - dt.timedelta(days=6)), "to": str(today)})
    conversation = api.ok("대화 생성", s, created)["conversationId"]
    for n in range(args.count):
        started = now_iso()
        result = session.sse(f"/conversations/{conversation}/messages", {"question": QUESTIONS[n % len(QUESTIONS)]})
        names = [name for name, _ in result["events"]]
        write(args.out, {
            "kind": "analysis", "startedAt": started, "endedAt": now_iso(), "ms": result["ms"],
            "firstEventMs": result["firstEventMs"], "httpStatus": result["status"],
            "events": sorted(set(names)), "deltas": names.count("delta"),
            "outcome": next((x for x in ("result", "clarification", "error", "http_error", "transport_error") if x in names), None),
            "error": (event(result, "error") or event(result, "http_error") or {}).get("code"),
        })
        print(f"analysis #{n + 1} {result['ms']}ms first={result['firstEventMs']}ms {sorted(set(names))}", flush=True)
        time.sleep(args.pause)
    return 0


MEMORY_QUERIES = ["친구와 함께 한 미션", "차례를 지키는 이야기", "이유를 쓴 답", "정리한 일", "기분 좋았던 일"]


def memory(args):
    """자녀마다 추억 검색 → 결과 카드의 시도(최대 3개)로 추억 설명. 검색은 임베딩, 설명은 LLM 1회다(하루 한도 검색 20·설명 10)."""
    api = Api()
    account = load_account(args.secrets)
    n = 0
    for index, child in enumerate(account["children"]):
        session = TokenSession(api, lambda child=child: student_token(api, account, child))
        for k in range(args.per_child):
            query = MEMORY_QUERIES[(index + k) % len(MEMORY_QUERIES)]
            started, t0 = now_iso(), time.perf_counter()
            s, found = session.call("POST", "/students/me/memories/search", {"query": query})
            search_ms = round((time.perf_counter() - t0) * 1000)
            found = found if isinstance(found, dict) else {}
            write(args.out, {"kind": "memory_search", "startedAt": started, "endedAt": now_iso(), "ms": search_ms, "httpStatus": s,
                             "state": found.get("state"), "cards": len(found.get("cards") or []),
                             "error": None if s == 200 else found.get("code")})
            attempts = [m["attemptId"] for c in found.get("cards") or [] for m in c.get("missions") or [] if m.get("attemptId")]
            print(f"memory search child{index} {search_ms}ms HTTP {s} {found.get('state')} attempts={len(attempts)}", flush=True)
            if not attempts:
                continue
            started, t0 = now_iso(), time.perf_counter()
            s, explained = session.call("POST", "/students/me/memories/explanations", {"query": query, "attemptIds": list(dict.fromkeys(attempts))[:3]})
            ms = round((time.perf_counter() - t0) * 1000)
            explained = explained if isinstance(explained, dict) else {}
            write(args.out, {"kind": "memory_explanation", "startedAt": started, "endedAt": now_iso(), "ms": ms, "httpStatus": s,
                             "state": explained.get("state"),
                             "error": None if s == 200 and explained.get("state") == "GENERATED" else explained.get("code") or explained.get("state")})
            n += 1
            print(f"memory explanation #{n} child{index} {ms}ms HTTP {s} {explained.get('state')}", flush=True)
            time.sleep(args.pause)
    return 0


def admin_token(api, env_file):
    """관리자 ID·비밀번호는 저장소 밖 env 파일(ADMIN_LOGIN=…, ADMIN_PASSWORD=…)에서 읽는다."""
    path = Path(env_file).resolve()
    if path == ROOT or ROOT in path.parents:
        raise SystemExit("--admin-env는 저장소 밖이어야 합니다.")
    values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)
    s, p = api.call("POST", "/auth/admin/login", {"loginId": values["ADMIN_LOGIN"].strip(), "password": values["ADMIN_PASSWORD"].strip()})
    return api.ok("관리자 로그인", s, p, (200,))["accessToken"]


class AdminSession:
    """관리자 access는 15분이면 만료된다. 401이면 다시 로그인한다(테마 초안은 30분 넘게 걸릴 수 있음)."""

    def __init__(self, api, env_file):
        self.api, self.env_file = api, env_file
        self.token = admin_token(api, env_file)

    def call(self, method, path, body=None):
        s, p = self.api.call(method, path, body, token=self.token)
        if s == 401:
            self.token = admin_token(self.api, self.env_file)
            s, p = self.api.call(method, path, body, token=self.token)
        return s, p


def poll(session, path, done, interval, limit):
    """완료 상태가 될 때까지 interval초마다 GET. 마지막 응답과 걸린 시간(ms)을 돌려준다."""
    start = time.perf_counter()
    payload = None
    while time.perf_counter() - start < limit:
        s, payload = session.call("GET", path)
        if s == 200 and done(payload):
            break
        time.sleep(interval)
    return payload, round((time.perf_counter() - start) * 1000)


def report(args):
    """관리자 재생성(POST /reports/{id}/regenerate) → 새 job이 COMPLETED·FAILED가 될 때까지. 서술 LLM이 다시 불린다."""
    session = AdminSession(Api(), args.admin_env)
    for n in range(args.count):
        started = now_iso()
        t0 = time.perf_counter()
        s, accepted = session.call("POST", f"/reports/{args.report_id}/regenerate")
        session.api.ok("리포트 재생성", s, accepted, (202,))
        job, _ = poll(session, f"/admin/jobs/{accepted['jobId']}",
                      lambda j: (j or {}).get("status") in ("COMPLETED", "FAILED"), args.interval, args.limit)
        ms = round((time.perf_counter() - t0) * 1000)
        write(args.out, {"kind": "report_weekly", "startedAt": started, "endedAt": now_iso(), "ms": ms,
                         "httpStatus": 200, "jobStatus": (job or {}).get("status"),
                         "error": None if (job or {}).get("status") == "COMPLETED" else (job or {}).get("failureReason") or "NOT_COMPLETED"})
        print(f"report #{n + 1} {ms}ms {(job or {}).get('status')}", flush=True)
        time.sleep(args.pause)
    return 0


def theme(args):
    """관리자 테마 초안 요청(POST /admin/theme-drafts) → GENERATING을 벗어날 때까지. learning 스케줄러(10초 주기) 대기가 포함된다."""
    session = AdminSession(Api(), args.admin_env)
    for n, grade in enumerate(args.grades):
        started = now_iso()
        t0 = time.perf_counter()
        body = {"grade": grade, "weekStart": args.week_start}
        s, draft = session.call("POST", "/admin/theme-drafts", body)
        session.api.ok("테마 초안 요청", s, draft, (201, 202))
        final, _ = poll(session, f"/admin/theme-drafts/{draft['draftId']}",
                        lambda d: (d or {}).get("status") != "GENERATING", args.interval, args.limit)
        ms = round((time.perf_counter() - t0) * 1000)
        status = (final or {}).get("status")
        write(args.out, {"kind": "theme_draft", "startedAt": started, "endedAt": now_iso(), "ms": ms, "httpStatus": 200,
                         "grade": grade, "draftStatus": status, "attempts": (final or {}).get("attempts"),
                         "failureCode": (final or {}).get("failureCode"),
                         "error": None if status == "READY" else (final or {}).get("failureCode") or status})
        print(f"theme #{n + 1} {grade} {ms}ms {status} attempts={(final or {}).get('attempts')}", flush=True)
        if args.discard and status in ("READY", "CHECK_FAILED", "FAILED"):
            session.call("POST", f"/admin/theme-drafts/{draft['draftId']}/discard", {})
    return 0


def pct(values, p):
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def summary(args):
    rows = [json.loads(line) for line in open(args.out, encoding="utf-8") if line.strip()]
    if args.since:
        rows = [r for r in rows if r["startedAt"] >= args.since]
    groups = {}
    for r in rows:
        key = r["kind"]
        if r["kind"] == "feedback":
            key = "feedback+followup" if r.get("followupSource") in ("LLM", "LLM_RETRY") else "feedback(only)"
        ok = r.get("httpStatus") == 200 and not r.get("error") and r.get("outcome", "result") not in ("error", "http_error", "transport_error")
        groups.setdefault(key, []).append((r, ok))
    print(f"{'종류':22} {'건수':>4} {'실패':>4} {'p50':>8} {'p95':>8} {'최대':>8} {'첫 이벤트 p50':>12}")
    for key, items in sorted(groups.items()):
        ms = [r["ms"] for r, ok in items if ok]
        first = [r["firstEventMs"] for r, ok in items if ok and r.get("firstEventMs") is not None]
        if not ms:
            print(f"{key:22} {len(items):>4} {len(items):>4}")
            continue
        print(f"{key:22} {len(items):>4} {len(items) - len(ms):>4} {pct(ms, .5):>8.0f} {pct(ms, .95):>8.0f} {max(ms):>8.0f} "
              f"{(statistics.median(first) if first else float('nan')):>12.0f}")
    if rows:
        print(f"기간 {min(r['startedAt'] for r in rows)} ~ {max(r['endedAt'] for r in rows)}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("judge")
    j.add_argument("--secrets", required=True)
    j.add_argument("--out", required=True)
    j.add_argument("--judgments", type=int, default=20)
    j.add_argument("--followups", type=int, default=20)
    j.add_argument("--max-turns", type=int, default=3, help="미션당 답변 수 상한(판정 최대 3회)")
    j.add_argument("--input-types", nargs="+", default=["NARRATIVE"])
    a = sub.add_parser("analyze")
    a.add_argument("--secrets", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--count", type=int, default=20)
    a.add_argument("--child", type=int, default=0, help="프리미엄 구독이 있는 자녀 순번")
    a.add_argument("--pause", type=float, default=2.0)
    r = sub.add_parser("report")
    r.add_argument("--admin-env", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--report-id", required=True, help="다시 만들 주간 리포트(서술 대상 상품·공유 켜짐)")
    r.add_argument("--count", type=int, default=5)
    r.add_argument("--interval", type=float, default=1.0)
    r.add_argument("--limit", type=float, default=600)
    r.add_argument("--pause", type=float, default=2.0)
    t = sub.add_parser("theme")
    t.add_argument("--admin-env", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--grades", nargs="+", default=["G3", "G4", "G5"])
    t.add_argument("--week-start", required=True, help="이번 주 이후 월요일(YYYY-MM-DD)")
    t.add_argument("--interval", type=float, default=5.0)
    t.add_argument("--limit", type=float, default=3600)
    t.add_argument("--discard", action="store_true", help="끝난 초안을 버림 처리해 게시 후보에 남기지 않음")
    m = sub.add_parser("memory")
    m.add_argument("--secrets", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--per-child", type=int, default=3, help="자녀마다 검색·설명 횟수(하루 한도 설명 10)")
    m.add_argument("--pause", type=float, default=2.0)
    s = sub.add_parser("summary")
    s.add_argument("--out", required=True)
    s.add_argument("--since", help="이 UTC ISO 시각 이후 표본만(재시작 구간을 버릴 때)")
    args = parser.parse_args(argv)
    if getattr(args, "out", None) and args.cmd != "summary":
        resolved = Path(args.out).resolve()
        if resolved == ROOT or ROOT in resolved.parents:
            raise SystemExit("--out은 저장소 밖이어야 합니다.")
    return {"judge": judge, "analyze": analyze, "memory": memory, "report": report, "theme": theme, "summary": summary}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
