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
  DEMO_OPS_ADMIN_LOGIN / DEMO_OPS_ADMIN_PASSWORD  공지·문의 답변·신고 처리용 SERVICE_OPS 관리자(#808, 없으면 DEMO_ADMIN_*)

#808 더미 가족 여러 명은 dummy854_data.py가 이 파일의 Api·solve_week를 가져다 쓴다.

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
    # #808: 더미 학생 한 명이 4주(20문제) 동안 같은 소재를 다시 쓰지 않게 20개로 늘림
    ("아빠와 함께 종이비행기를 멀리 날린 일", "날개 모양을 바꾸면 나는 거리가 달라지기 때문이야"),
    ("교실 어항의 금붕어 먹이 당번을 한 일", "맡은 일을 꾸준히 해야 모두가 믿을 수 있기 때문이야"),
    ("비 온 뒤 운동장에서 무지개를 본 일", "햇빛과 물방울이 만나면 색이 나뉘어 보이기 때문이야"),
    ("이웃 할아버지께 먼저 인사드린 일", "작은 인사가 서로를 더 가깝게 만들어 주기 때문이야"),
    ("집에서 콩나물을 길러 본 일", "물을 자주 주고 빛을 가려야 잘 자라기 때문이야"),
]


# 설명 카드(FN-RPT-09)용 M2 입력(api-spec 4.2.2, #668). 저장소 시드 G5 미션(demo_missions.sql)만 둔다.
# 서술은 핵심어 묶음(`핵심어(비슷한 말)`), 논술은 글 종류. 운영 시드 migration이 아니라 시연 계정 준비에서만 넣는다.
# 관리자 화면·초안으로 만든 테마 미션은 --m2-input JSON({"미션 code": {"keywords": [...]} 또는 {"essayType": "..."}})으로 더한다.
M2_INPUTS = {
    "DEMO-11-G5-ANALYZE": {"keywords": ["온도(따뜻해짐, 식음)", "열(따뜻한 기운)", "비슷해짐(같아짐)"]},
    "DEMO-12-G5-EVALUATE": {"essayType": "주장"},
    "DEMO-13-G5-CREATE": {"keywords": ["새 규칙(약속)", "공평(공정)", "참여(함께)"]},
    "DEMO-15-G5-REFLECT": {"keywords": ["고쳐 쓰기(수정)", "달라진 점(나아진 점)", "까닭(이유)"]},
}


def topic(week_start, day, seed=0):
    """주(월요일)·요일마다 정해진 소재. 연속 4주는 서로 겹치지 않는다.
    seed(#808 더미 학생의 학년 안 순번)가 다르면 같은 주·요일에도 소재가 달라 친구 생각 글이 서로 구분된다."""
    weeks = (dt.date.fromisoformat(week_start) - dt.date(2026, 1, 5)).days // 7
    return TOPICS[(weeks * len(DAYS) + DAYS.index(day) + seed) % len(TOPICS)]


def answer_body(mission, week_start, day, seed=0):
    """입력 방식별 제출 본문(api-spec 3.1). 선택형은 미션 선택지에서 고른다."""
    kind = mission.get("inputType", "NARRATIVE")
    about, why = topic(week_start, day, seed)
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
    def parent(self, creds=None):
        """creds가 없으면 시연 학부모(환경 변수), 있으면 (로그인 ID, 비밀번호) — #808 더미 학부모"""
        login, password = creds or (os.environ["DEMO_PARENT_LOGIN"], os.environ["DEMO_PARENT_PASSWORD"])
        s, p, ck = self.call("POST", "/auth/parent/login", {"loginId": login, "password": password})
        self.ok("학부모 로그인", s, p, (200,))
        return p["accessToken"], ck

    def admin(self):
        s, p, _ = self.call("POST", "/auth/admin/login", {"loginId": os.environ["DEMO_ADMIN_LOGIN"],
                                                          "password": os.environ["DEMO_ADMIN_PASSWORD"]})
        self.ok("관리자 로그인", s, p, (200,))
        return p["accessToken"]

    def ops_admin(self):
        """공지·문의·신고 처리는 ADMIN + SERVICE_OPS 권한(api-spec 2.8)"""
        login = os.environ.get("DEMO_OPS_ADMIN_LOGIN") or os.environ["DEMO_ADMIN_LOGIN"]
        password = os.environ.get("DEMO_OPS_ADMIN_PASSWORD") or os.environ["DEMO_ADMIN_PASSWORD"]
        s, p, _ = self.call("POST", "/auth/admin/login", {"loginId": login, "password": password})
        self.ok("운영 관리자 로그인", s, p, (200,))
        return p["accessToken"]

    def children(self, ptok):
        s, p, _ = self.call("GET", "/children", token=ptok)
        return {c["nickname"]: c for c in self.ok("자녀 목록", s, p, (200,))["items"]}

    def student(self, nickname, creds=None):
        ptok, ck = self.parent(creds)
        child = self.children(ptok).get(nickname)
        if not child:
            raise SystemExit(f"자녀 '{nickname}'이 없음. 먼저 children 명령으로 등록")
        s, p, _ = self.call("POST", "/auth/student-sessions", {"childId": child["id"]}, ptok, ck)
        self.ok("학생 세션", s, p, (200,))
        return p["accessToken"], child


def cmd_children(api, args):
    """시연 학부모 아래 가상 자녀를 등록한다. 이미 있으면 그대로 두고, 필수 동의 문서 새 버전 시행 뒤면 재동의한다."""
    ptok, _ = api.parent()
    _, docs, _ = api.call("GET", "/consent-documents")

    def agree(*kinds):
        return [{"documentId": d["documentId"], "version": d["version"], "agreed": True}
                for d in docs["items"] if d["kind"] in kinds]
    s, me, _ = api.call("GET", "/me", token=ptok)
    if api.ok("내 정보", s, me, (200,)).get("nextAction") == "CONSENT_REQUIRED":
        # 새로 가입했거나 계정 필수 문서(이용약관·개인정보) 새 버전이 시행된 시연 학부모(#894)
        s, p, _ = api.call("POST", "/me/consents", {"consents": agree("TERMS", "PRIVACY")}, ptok)
        api.ok("계정 동의", s, p, (200, 201, 204))
        print("학부모 계정 동의 저장")
    have = api.children(ptok)
    consents = agree("GUARDIAN")
    year = dt.datetime.now(KST).year
    for spec in args.child:
        nickname, grade = spec.rsplit(":", 1)
        if nickname in have:
            if have[nickname].get("guardianConsentRequired"):
                # 법정대리인 동의서 새 버전 시행(#894)·철회: 학생 세션 전에 자녀 단위 재동의
                s, p, _ = api.call("POST", "/me/consents", {"childId": have[nickname]["id"], "consents": consents}, ptok)
                api.ok(f"{nickname} 법정대리인 재동의", s, p, (200, 201, 204))
                print(f"{nickname}: 법정대리인 재동의")
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


def cmd_m2_rubric(api, args):
    """대상 주 게시 테마의 서술·논술 미션 기준표에 M2 입력을 채운다: 공개 기준표 복사 + keywords/essayType →
    새 기준표 버전 → 검토 승인 → 재게시(api-spec 2.8, P07). 이미 있으면 그대로 둔다(다시 실행해도 같은 결과).
    공개 중이 아닌 수정본이 걸려 있는 미션은 남의 편집을 게시하지 않도록 건드리지 않고 실패한다."""
    inputs = dict(M2_INPUTS)
    if args.m2_input:
        with open(args.m2_input, encoding="utf-8") as f:
            inputs.update(json.load(f))
    atok = api.admin()
    themes, seen, missing, blocked = [], {}, [], []
    for week in args.weeks.split(","):
        s, p, _ = api.call("GET", f"/admin/weekly-themes?grade={args.grade}&weekStart={week}&status=PUBLISHED", token=atok)
        for item in api.ok("테마 목록", s, p, (200,))["items"]:
            s, theme, _ = api.call("GET", f"/admin/weekly-themes/{item['themeId']}", token=atok)
            themes.append((week, api.ok("테마 상세", s, theme, (200,))))
    if not themes:
        raise SystemExit("대상 주에 게시된 테마가 없음")
    for week, theme in themes:
        ready = []
        for d in theme["days"]:
            mid = d["missionId"]
            if mid not in seen:
                seen[mid] = m2_fill(api, atok, mid, inputs, args.dry_run, missing, blocked)
            if seen[mid]:
                ready.append(seen[mid])
        narrative = sorted({t for kind, t in ready if kind == "NARRATIVE"})
        # 설명은 생각 유형이 겹치지 않는 M2 점수 답변 최대 3개. 초5 M2 활성 범위는 서술이라 서술 3개가 있어야 카드 3개
        print(f"{week} {args.grade}: M2 입력 서술 {len(narrative)}유형 {narrative}, 논술 {sum(k == 'ESSAY' for k, _ in ready)}개")
    if missing or blocked:
        raise SystemExit("M2 입력을 채우지 못함: " + ", ".join(
            [f"{c}(입력 없음, --m2-input으로 추가)" for c in missing] + [f"{c}(공개 안 된 수정본 있음)" for c in blocked]))


def m2_fill(api, atok, mission_id, inputs, dry_run, missing, blocked):
    """미션 하나의 공개 기준표를 확인·보강한다. 서술·논술이면 (입력 방식, 생각 유형), 아니면 None"""
    s, m, _ = api.call("GET", f"/admin/missions/{mission_id}", token=atok)
    m = api.ok("미션 상세", s, m, (200,))
    version = next(v for v in m["versions"] if v["version"] == m["publishedVersion"])
    kind = version["inputType"]
    if kind not in ("NARRATIVE", "ESSAY"):
        return None
    rubric = next((r for r in m["rubrics"] if r["version"] == m["publishedRubricVersion"]), None)
    field = "keywords" if kind == "NARRATIVE" else "essayType"
    if rubric and rubric.get(field):
        print(f"  {m['code']} {kind}: 기준표 v{rubric['version']}에 {field} 있음")
        return kind, version["thinkingType"]
    want = (inputs.get(m["code"]) or {}).get(field)
    if not want:
        missing.append(m["code"])
        return None
    if (m["currentVersion"], m["currentRubricVersion"]) != (m["publishedVersion"], m["publishedRubricVersion"]):
        blocked.append(m["code"])
        return None
    if dry_run:
        print(f"  {m['code']} {kind}: {field} 채울 예정(--dry-run)")
        return kind, version["thinkingType"]
    keep = ("code", "label", "description", "points", "commonErrors", "goodThought", "judgeVerified", "standardCode")
    body = {"elements": [{k: e.get(k) for k in keep} for e in rubric["elements"]],
            "answerKey": rubric.get("answerKey"), "exampleAnswer": rubric.get("exampleAnswer"),
            "forbiddenTerms": rubric.get("forbiddenTerms") or [], "hints": rubric.get("hints") or [],
            "keywords": rubric.get("keywords") or [], "essayType": rubric.get("essayType"), field: want}
    s, m2, _ = api.call("PUT", f"/admin/missions/{mission_id}/rubric", body, atok)
    m2 = api.ok(f"{m['code']} 기준표 저장", s, m2, (200, 201))
    pin = {"missionVersion": m2["currentVersion"], "rubricVersion": m2["currentRubricVersion"]}
    s, p, _ = api.call("POST", f"/admin/missions/{mission_id}/review", {**pin, "result": "APPROVED",
                                                                       "comment": "#668 시연 설명 카드용 M2 입력 보강"}, atok)
    api.ok(f"{m['code']} 검토", s, p, (200,))
    s, p, _ = api.call("POST", f"/admin/missions/{mission_id}/publish", {}, atok)
    p = api.ok(f"{m['code']} 재게시", s, p, (200,))
    print(f"  {m['code']} {kind}: 기준표 v{rubric['version']} → v{p['publishedRubricVersion']} {field} 채움·재게시")
    return kind, version["thinkingType"]


def theme_answer(api, theme_id):
    s, p, _ = api.call("GET", f"/admin/weekly-themes/{theme_id}", token=api.admin())
    return api.ok("테마 상세", s, p, (200,)).get("answer")


def solve_mission(api, stok, mission_id, context, week_start, day, seed=0):
    """시작 → 답변 → 피드백(SSE) → 마무리 → 돌아보기. 진행 중 시도는 이어서 끝낸다."""
    s, att, _ = api.call("POST", f"/missions/{mission_id}/attempts", {"context": context}, stok)
    api.ok(f"{day} 시작", s, att, (200, 201))
    aid = att["attemptId"]
    _, mission, _ = api.call("GET", f"/missions/{mission_id}", token=stok)
    answers = att.get("answers") or []
    if answers:
        answer_id = answers[-1]["answerId"]
    else:
        body = {"inputType": mission.get("inputType", "NARRATIVE"), **answer_body(mission, week_start, day, seed),
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
    solve_week(api, stok, args.child, skip_pick=args.skip_pick)


def solve_week(api, stok, label, limit=None, finish=True, skip_pick=False, seed=0):
    """이번 주 테마를 월요일부터 열린 요일 순서로 푼다. limit이면 완료 요일이 limit개가 될 때까지만(#808 무리별 주 문제 수),
    finish=False면 정답 고르기·종료 이야기를 하지 않는다. 끝난 요일은 건너뛰므로 다시 불러도 같은 결과다."""
    s, theme, _ = api.call("GET", "/students/me/weekly-theme", token=stok)
    theme = api.ok("이번 주 테마", s, theme, (200,))
    week = theme["weekStart"]
    print(f"{label}: {week} 주 테마, 요일 상태 {[(d['day'], d['state'], d.get('attemptStatus')) for d in theme['days']]}")
    api.call("POST", "/students/me/weekly-theme/story-views", {"kind": "INTRO"}, stok)
    done = sum(d.get("attemptStatus") == "COMPLETED" for d in theme["days"])
    for d in theme["days"]:
        if limit is not None and done >= limit:
            break
        if d.get("attemptStatus") == "COMPLETED":
            continue
        if d["state"] != "OPEN":
            raise SystemExit(f"{d['day']}가 {d['state']}라 지금 풀 수 없음(무료는 금·토, 프리미엄은 일요일까지)")
        solve_mission(api, stok, d["missionId"], "THEME_DAY", week, d["day"], seed)
        done += 1
        print(f"  {d['day']} 완료")
    if not finish:
        return
    s, theme, _ = api.call("GET", "/students/me/weekly-theme", token=stok)
    if theme.get("ending") != "ENDED" and not skip_pick:
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
    p = sub.add_parser("m2-rubric", help="대상 주 테마 서술·논술 미션 기준표에 M2 입력 보강(설명 카드용)")
    p.add_argument("--weeks", required=True, help="월요일 날짜, 쉼표 구분")
    p.add_argument("--grade", default="G5")
    p.add_argument("--m2-input", help="시드 밖 미션의 M2 입력 JSON 파일")
    p.add_argument("--dry-run", action="store_true", help="채울 미션만 보여 주고 저장하지 않음")
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
    {"children": cmd_children, "themes": cmd_themes, "m2-rubric": cmd_m2_rubric, "solve": cmd_solve,
     "decorate": cmd_decorate, "verify": cmd_verify}[args.cmd](api, args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
