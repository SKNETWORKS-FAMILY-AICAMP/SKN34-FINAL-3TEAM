"""시연 계정 데이터 준비 (#624): 지난 회차 완료 기록을 실제 공개 API 흐름으로 만든다.

DB에 직접 쓰지 않는다. 학부모·관리자 로그인 → 학생 세션 → 이번 주 테마 5문제 풀이·정답 고르기 →
(다음 주 월요일 이후) 앨범 확인·추억의 벽·가구 스킨을 차례로 부른다. "이번 주"는 서버 시계 기준이므로
지난 주 회차는 core·learning 시계를 그 주 토요일로 옮긴 상태(demo-clock.Dockerfile)에서 `solve`를 부른다.
순서·되돌리기는 infrastructure/aws/README.md "시연 계정 데이터 준비(#624)"를 따른다.

환경 변수(값은 출력하지 않음):
  DEMO_API_BASE     예: https://<데모 도메인>/api/v1, kind는 http://127.0.0.1/api/v1
  DEMO_API_HOST     Host 헤더가 따로 필요할 때(kind: api.sagomungchi.local)
  DEMO_ORIGIN       Origin 헤더(CSRF 검사). 기본 http://localhost:5173
  DEMO_PARENT_LOGIN / DEMO_PARENT_PASSWORD   시연 학부모(ID·비밀번호 로그인)
  DEMO_ADMIN_LOGIN / DEMO_ADMIN_PASSWORD     정답 조회·테마 게시 확인용 CONTENT 관리자

출력에는 닉네임·상태 코드·건수만 남기고 토큰·비밀번호·presigned URL·학생 답변 원문은 남기지 않는다.
가상 학생과 저장소의 자체 미션만 대상으로 한다(NFR-SEC-07).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid

KST = dt.timezone(dt.timedelta(hours=9))
DAYS = ["MON", "TUE", "WED", "THU", "FRI"]

# 자체 작성한 가상 학생 답변 소재. 회차·요일마다 다른 소재가 들어가 추억 검색에서 회차가 구분된다.
TOPICS = [
    ("우리 집 고양이 나비가 상자 속을 좋아하는 것", "좁은 곳이 오히려 마음을 편하게 해 주기 때문이야"),
    ("비 오는 날 친구와 우산 하나를 같이 쓴 일", "함께 나누면 둘 다 덜 젖고 더 즐겁기 때문이야"),
    ("할머니 댁 텃밭에서 방울토마토를 딴 일", "직접 기른 것은 더 소중하게 느껴지기 때문이야"),
    ("운동회 이어달리기에서 바통을 놓친 일", "실수해도 다시 뛰면 끝까지 해낼 수 있기 때문이야"),
    ("도서관에서 공룡 책을 빌려 읽은 일", "궁금한 것을 찾아 읽으면 생각이 넓어지기 때문이야"),
    ("동생과 블록으로 높은 탑을 쌓은 일", "서로 순서를 정하면 무너지지 않게 쌓을 수 있기 때문이야"),
    ("겨울에 눈사람을 만들고 목도리를 둘러 준 일", "작은 것을 더하면 훨씬 따뜻해 보이기 때문이야"),
    ("학교 화단에 해바라기 씨앗을 심은 일", "햇빛과 물을 꾸준히 주어야 싹이 트기 때문이야"),
    ("강아지 산책 순서를 가족과 나눈 일", "규칙을 정하면 아무도 서운하지 않기 때문이야"),
    ("시장에서 붕어빵 값을 계산해 본 일", "계산을 미리 하면 돈을 알맞게 낼 수 있기 때문이야"),
    ("바닷가에서 소라 껍데기를 모은 일", "모양을 비교하면 저마다 다른 점이 보이기 때문이야"),
    ("미술 시간에 종이로 별 모빌을 만든 일", "균형을 맞추어야 모빌이 기울지 않기 때문이야"),
    ("캠핑에서 별자리를 찾아본 일", "밝은 별을 먼저 찾으면 나머지를 이어 볼 수 있기 때문이야"),
    ("친구 생일 카드에 그림을 그려 준 일", "마음을 담으면 작은 선물도 크게 느껴지기 때문이야"),
    ("자전거 타기를 처음 연습한 일", "넘어져도 균형 잡는 법을 조금씩 알게 되기 때문이야"),
]


def topic(week_start, day):
    """주(월요일)·요일마다 정해진 소재. 연속 3주는 서로 겹치지 않는다."""
    weeks = (dt.date.fromisoformat(week_start) - dt.date(2026, 1, 5)).days // 7
    return TOPICS[(weeks * len(DAYS) + DAYS.index(day)) % len(TOPICS)]


def answer_body(mission, week_start, day):
    """입력 방식별 제출 본문(api-spec 3.1). 선택형은 미션 선택지에서 고른다."""
    kind = mission.get("inputType", "NARRATIVE")
    about, why = topic(week_start, day)
    title = mission.get("title") or "이번 문제"
    choices = [c["id"] for c in mission.get("choices") or []]
    if kind == "NARRATIVE":
        return {"text": f"'{title}' 문제를 보고 {about}이 떠올랐어. 나는 차근차근 살펴보는 게 중요하다고 생각해. 왜냐하면 {why}."}
    if kind == "ESSAY":
        return {"essay": {"claim": f"'{title}'에서 나는 서로 의견을 듣고 정하는 것이 좋다고 생각해.",
                          "reasons": [f"{about}을 떠올려 보면 함께 정할 때 더 잘 됐어.", f"{why}."],
                          "rebuttal": "시간이 더 걸린다는 의견도 있지만 모두가 납득하면 다시 다툴 일이 줄어들어."}}
    if kind == "SOLUTION_STEPS":
        return {"finalAnswer": "12", "steps": [f"{about}처럼 알려 준 수를 먼저 정리한다.", "필요한 식을 세워 차례로 계산한다."]}
    if kind == "CHOICE":
        return {"choiceIds": choices[:1]}
    if kind == "ORDERING":
        return {"choiceIds": choices}
    if kind == "CLASSIFICATION":
        groups = [g["id"] for g in mission.get("categories") or []]
        return {"assignments": [{"choiceId": c, "categoryId": groups[0]} for c in choices]}
    raise SystemExit(f"지원하지 않는 입력 방식: {kind}")


class Api:
    URL_RE = re.compile(r"https?://\S+")

    def __init__(self):
        self.base = os.environ["DEMO_API_BASE"].rstrip("/")
        self.host = os.environ.get("DEMO_API_HOST")
        self.origin = os.environ.get("DEMO_ORIGIN", "http://localhost:5173")

    def call(self, method, path, body=None, token=None, cookie=None, headers=None, raw=False, timeout=180):
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
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload, status, hdr = r.read(), r.status, r.headers
        except urllib.error.HTTPError as e:
            payload, status, hdr = e.read(), e.code, e.headers
        cookies = "; ".join(c.split(";", 1)[0] for c in hdr.get_all("Set-Cookie") or [])
        if raw:
            return status, payload.decode(errors="replace"), cookies
        try:
            parsed = json.loads(payload) if payload else None
        except ValueError:
            parsed = {"raw": self.URL_RE.sub("<url>", payload.decode(errors="replace")[:200])}
        return status, parsed, cookies

    def ok(self, label, status, payload, allowed=(200, 201, 202, 204)):
        if status not in allowed:
            code = payload.get("code") if isinstance(payload, dict) else None
            raise SystemExit(f"{label} 실패: HTTP {status} {code or ''}".strip())
        return payload

    # --- 로그인 ---
    def parent(self):
        s, p, ck = self.call("POST", "/auth/parent/login", {"loginId": os.environ["DEMO_PARENT_LOGIN"],
                                                            "password": os.environ["DEMO_PARENT_PASSWORD"]})
        self.ok("학부모 로그인", s, p, (200,))
        return p["accessToken"], ck

    def admin(self):
        s, p, _ = self.call("POST", "/auth/admin/login", {"loginId": os.environ["DEMO_ADMIN_LOGIN"],
                                                          "password": os.environ["DEMO_ADMIN_PASSWORD"]})
        self.ok("관리자 로그인", s, p, (200,))
        return p["accessToken"]

    def children(self, ptok):
        s, p, _ = self.call("GET", "/children", token=ptok)
        return {c["nickname"]: c for c in self.ok("자녀 목록", s, p, (200,))["items"]}

    def student(self, nickname):
        ptok, ck = self.parent()
        child = self.children(ptok).get(nickname)
        if not child:
            raise SystemExit(f"자녀 '{nickname}'이 없음. 먼저 children 명령으로 등록")
        s, p, _ = self.call("POST", "/auth/student-sessions", {"childId": child["id"]}, ptok, ck)
        self.ok("학생 세션", s, p, (200,))
        return p["accessToken"], child


def cmd_children(api, args):
    """시연 학부모 아래 가상 자녀를 등록한다. 이미 있으면 그대로 둔다."""
    ptok, _ = api.parent()
    _, docs, _ = api.call("GET", "/consent-documents")

    def agree(*kinds):
        return [{"documentId": d["documentId"], "version": d["version"], "agreed": True}
                for d in docs["items"] if d["kind"] in kinds]
    s, p, _ = api.call("GET", "/children", token=ptok)
    if s == 403 and (p or {}).get("code") == "CONSENT_REQUIRED":
        # 새로 가입한 시연 학부모: 계정 필수 동의(이용약관·개인정보)부터 저장
        s, p, _ = api.call("POST", "/me/consents", {"consents": agree("TERMS", "PRIVACY")}, ptok)
        api.ok("계정 동의", s, p, (200, 201, 204))
        print("학부모 계정 동의 저장")
    have = api.children(ptok)
    consents = agree("GUARDIAN")
    year = dt.datetime.now(KST).year
    for spec in args.child:
        nickname, grade = spec.rsplit(":", 1)
        if nickname in have:
            print(f"{nickname}: 이미 있음(grade {have[nickname]['grade']})")
            continue
        s, p, _ = api.call("POST", "/children", {"nickname": nickname, "grade": int(grade),
                                                 "birthYear": year - 7 - int(grade), "consents": consents}, ptok)
        api.ok(f"{nickname} 등록", s, p, (200, 201))
        print(f"{nickname}: 등록(grade {grade})")


def cmd_themes(api, args):
    """대상 주·학년 테마가 게시돼 있는지 확인한다. 없으면 실패(테마 작성·게시는 관리자 화면에서)."""
    atok = api.admin()
    missing = 0
    for week in args.weeks.split(","):
        for grade in args.grades.split(","):
            s, p, _ = api.call("GET", f"/admin/weekly-themes?grade={grade}&weekStart={week}&status=PUBLISHED", token=atok)
            items = api.ok("테마 목록", s, p, (200,))["items"]
            state = "게시됨" if items else "없음"
            missing += not items
            print(f"{week} {grade}: {state}")
    if missing:
        raise SystemExit(f"게시되지 않은 테마 {missing}개")


def theme_answer(api, theme_id):
    s, p, _ = api.call("GET", f"/admin/weekly-themes/{theme_id}", token=api.admin())
    return api.ok("테마 상세", s, p, (200,)).get("answer")


def solve_mission(api, stok, mission_id, context, week_start, day):
    """시작 → 답변 → 피드백(SSE) → 마무리 → 돌아보기. 진행 중 시도는 이어서 끝낸다."""
    s, att, _ = api.call("POST", f"/missions/{mission_id}/attempts", {"context": context}, stok)
    api.ok(f"{day} 시작", s, att, (200, 201))
    aid = att["attemptId"]
    _, mission, _ = api.call("GET", f"/missions/{mission_id}", token=stok)
    answers = att.get("answers") or []
    if answers:
        answer_id = answers[-1]["answerId"]
    else:
        body = {"inputType": mission.get("inputType", "NARRATIVE"), **answer_body(mission, week_start, day),
                "dictatedByGuardian": False}
        s, a, _ = api.call("POST", f"/attempts/{aid}/answers", body, stok, headers={"Idempotency-Key": str(uuid.uuid4())})
        answer_id = api.ok(f"{day} 답변", s, a, (200, 201))["answerId"]
    s, stream, _ = api.call("POST", f"/answers/{answer_id}/feedback", token=stok,
                            headers={"Accept": "text/event-stream"}, raw=True, timeout=300)
    if s != 200 or not re.search(r'"status": ?"DONE"', stream):
        raise SystemExit(f"{day} 피드백이 DONE이 아님(HTTP {s})")
    s, p, _ = api.call("POST", f"/attempts/{aid}/finish", {}, stok)
    api.ok(f"{day} 마무리", s, p)
    s, p, _ = api.call("POST", f"/attempts/{aid}/reflection", {"difficulty": "NORMAL"}, stok)
    api.ok(f"{day} 돌아보기", s, p, (200, 201, 204, 409))


def cmd_solve(api, args):
    """서버 시계 기준 이번 주 테마를 끝낸다: 원문 공개 → 시작 이야기 → 남은 요일 풀이 → 정답 고르기 → 종료 이야기."""
    stok, child = api.student(args.child)
    s, p, _ = api.call("PUT", "/students/me/sharing-preferences", {"parentSharingEnabled": True}, stok)
    api.ok("원문 공개", s, p)
    s, theme, _ = api.call("GET", "/students/me/weekly-theme", token=stok)
    theme = api.ok("이번 주 테마", s, theme, (200,))
    week = theme["weekStart"]
    print(f"{args.child}: {week} 주 테마, 요일 상태 {[(d['day'], d['state'], d.get('attemptStatus')) for d in theme['days']]}")
    api.call("POST", "/students/me/weekly-theme/story-views", {"kind": "INTRO"}, stok)
    for d in theme["days"]:
        if d.get("attemptStatus") == "COMPLETED":
            continue
        if d["state"] != "OPEN":
            raise SystemExit(f"{d['day']}가 {d['state']}라 지금 풀 수 없음(무료는 금·토, 프리미엄은 일요일까지)")
        solve_mission(api, stok, d["missionId"], "THEME_DAY", week, d["day"])
        print(f"  {d['day']} 완료")
    s, theme, _ = api.call("GET", "/students/me/weekly-theme", token=stok)
    if theme.get("ending") != "ENDED" and not args.skip_pick:
        answer = theme_answer(api, theme["themeId"])
        if answer is None:
            print("  정답 후보가 없는 테마라 정답 고르기 생략")
        else:
            s, p, _ = api.call("POST", "/students/me/weekly-theme/answer-picks", {"pick": answer}, stok)
            api.ok("정답 고르기", s, p, (200,))
            print(f"  정답 고르기 correct={p.get('correct')} ending={p.get('ending')}")
    s, p, _ = api.call("POST", "/students/me/weekly-theme/story-views", {"kind": "OUTRO"}, stok)
    print(f"  종료 이야기 열람 HTTP {s}")
    s, theme, _ = api.call("GET", "/students/me/weekly-theme", token=stok)
    print(f"  completed={theme.get('completed')} finished={theme.get('finished')} ending={theme.get('ending')}")


def album(api, stok):
    s, p, _ = api.call("GET", "/students/me/album?size=100", token=stok)
    return api.ok("앨범", s, p, (200,))["items"]


def cmd_decorate(api, args):
    """지난 회차가 앨범에 보인 뒤(다음 주 월요일 이후): 앨범 확인 → 추억의 벽 → 가구 스킨 해금·착용.
    가장 최근 회차는 --keep-newest-unseen이면 확인하지 않아 '새 액자' 표시를 남긴다."""
    stok, _ = api.student(args.child)
    items = album(api, stok)
    if len(items) < args.min_frames:
        raise SystemExit(f"앨범 액자 {len(items)}개 < {args.min_frames}")
    for i, it in enumerate(items):
        if args.keep_newest_unseen and i == 0:
            continue
        api.call("POST", f"/students/me/album/{it['themeId']}/{it['weekStart']}/seen", token=stok)
    slots = [{"slotNo": n + 1, "themeId": it["themeId"], "weekStart": it["weekStart"]} for n, it in enumerate(items[:6])]
    s, p, _ = api.call("PUT", "/students/me/room/frame-slots", {"slots": slots}, stok)
    print(f"{args.child}: 액자 {len(items)}개, 벽 슬롯 {len(api.ok('추억의 벽', s, p, (200,))['slots'])}개")
    if not args.furniture:
        return
    s, look, _ = api.call("GET", "/students/me/preferences", token=stok)
    look = api.ok("꾸미기 조회", s, look, (200,))
    equip = {}
    for code in args.furniture.split(","):
        s, p, _ = api.call("POST", f"/students/me/look-items/{code}/unlock", {}, stok,
                           headers={"Idempotency-Key": str(uuid.uuid4())})
        api.ok(f"{code} 해금", s, p, (200,))
        s, items_, _ = api.call("GET", "/students/me/look-items", token=stok)
        slot = next(x["slot"] for x in items_["items"] if x["itemKey"] == code)
        equip[slot] = code
    s, p, _ = api.call("PUT", "/students/me/preferences",
                       {"theme": look["theme"], "companion": look["companion"], "equipped": equip}, stok)
    api.ok("가구 착용", s, p, (200,))
    print(f"  가구 착용 {sorted(equip)}")


def cmd_verify(api, args):
    """화면에 나올 것을 API로 확인한다. 추억 검색은 하루 한도 20회 중 1회를 쓴다."""
    stok, child = api.student(args.child)
    items = album(api, stok)
    print(f"{args.child}: 앨범 {len(items)}개 {[(i['weekStart'], i.get('seen'), i.get('displayed')) for i in items]}")
    if items:
        s, d, _ = api.call("GET", f"/students/me/album/{items[0]['themeId']}/{items[0]['weekStart']}", token=stok)
        print(f"  최근 회차 상세 HTTP {s} 문제 {len(d.get('missions') or [])}개 엔딩 seen={((d.get('ending') or {}).get('seen'))}")
    if args.query:
        s, r, _ = api.call("POST", "/students/me/memories/search", {"query": args.query}, stok)
        cards = (r or {}).get("cards") or []
        print(f"  추억 검색 HTTP {s} {(r or {}).get('state')} 결과 {[c.get('weekStart') for c in cards]}")
    s, slots, _ = api.call("GET", "/students/me/room/frame-slots", token=stok)
    print(f"  추억의 벽 슬롯 {len((slots or {}).get('slots') or [])}개")
    s, look, _ = api.call("GET", "/students/me/preferences", token=stok)
    eq = (look or {}).get("equipped") or {}
    print(f"  가구 착용 DESK={eq.get('DESK')} WALL={eq.get('WALL')} WARDROBE={eq.get('WARDROBE')}")
    ptok, _ = api.parent()
    s, reps, _ = api.call("GET", f"/children/{child['id']}/reports", token=ptok)
    reps = api.ok("리포트 목록", s, reps, (200,))["items"]
    for kind in ("WEEKLY", "DAILY"):
        # 기록 없는 날(일요일 등)의 NO_RECORD 리포트는 건너뛰고 내용이 있는 최근 리포트를 본다
        latest = [r for r in reps if r["periodType"] == kind and r["status"] == "COMPLETED" and r["state"] != "NO_RECORD"]
        latest.sort(key=lambda r: r["period"]["from"], reverse=True)
        if not latest:
            print(f"  {kind} 리포트 없음")
            continue
        r = latest[0]
        s, body, _ = api.call("GET", f"/reports/{r['reportId']}", token=ptok)
        ex = (body or {}).get("explanations")
        cards = len((ex or {}).get("items") or []) if isinstance(ex, dict) else len(ex or [])
        state = ex.get("state") if isinstance(ex, dict) else None
        print(f"  최근 {kind} {r['period']['from']}~{r['period']['to']} state={r['state']} 설명 카드 {cards}개 {state or ''}".rstrip())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("children", help="가상 자녀 등록(닉네임:학년)")
    p.add_argument("--child", action="append", required=True, help="예: 시연3학년:3")
    p = sub.add_parser("themes", help="대상 주·학년 테마 게시 확인")
    p.add_argument("--weeks", required=True, help="월요일 날짜, 쉼표 구분")
    p.add_argument("--grades", default="G3,G5")
    p = sub.add_parser("solve", help="서버 시계 기준 이번 주 테마 끝내기")
    p.add_argument("--child", required=True)
    p.add_argument("--skip-pick", action="store_true", help="정답 고르기 생략(엔딩 전 상태)")
    p = sub.add_parser("decorate", help="앨범 확인·추억의 벽·가구 스킨")
    p.add_argument("--child", required=True)
    p.add_argument("--min-frames", type=int, default=1)
    p.add_argument("--furniture", help="해금·착용할 가구 look_item 코드, 쉼표 구분")
    p.add_argument("--keep-newest-unseen", action="store_true")
    p = sub.add_parser("verify", help="앨범·검색·벽·가구·리포트 확인")
    p.add_argument("--child", required=True)
    p.add_argument("--query", help="추억 검색 질문(하루 한도 1회 사용)")
    args = ap.parse_args()
    api = Api()
    {"children": cmd_children, "themes": cmd_themes, "solve": cmd_solve,
     "decorate": cmd_decorate, "verify": cmd_verify}[args.cmd](api, args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
