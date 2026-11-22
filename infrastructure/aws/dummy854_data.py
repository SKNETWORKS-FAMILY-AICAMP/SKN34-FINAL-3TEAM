"""#808 전체 서비스 시연용 더미 가족 데이터: 가족 목록(dummy854-families.json)의 학생 여러 명을 공개 API로 움직인다.

계획은 docs/report/infra.md 9.7.6, 실행 순서는 infrastructure/aws/README.md "전체 서비스 더미 데이터 (#808)".
DB에 직접 쓰지 않는다(시험 구독만 add-dummy854-subscriptions.sql). 테마·미션·가구·소품은 만들지 않고 있는 것만 쓴다(#890).
"이번 주"는 서버 시계 기준이라 W1~W3은 core·learning 시험 시계(demo-clock.Dockerfile)를 옮긴 상태에서 부른다.

환경 변수는 demo_account_data.py와 같다(DEMO_API_BASE·DEMO_API_HOST·DEMO_ORIGIN, 시연 학부모 DEMO_PARENT_*,
CONTENT 관리자 DEMO_ADMIN_*, 운영 관리자 DEMO_OPS_ADMIN_*). 더미 학부모 비밀번호는 prepare_accounts.py --families가 만든
저장소 밖 비밀 파일(--secrets)에서 읽는다. 출력에는 별명·건수·상태 코드만 남긴다.
문구(답변·질문·문의·공지)는 모두 자체 작성한 가상 내용이다(NFR-SEC-07).
"""
import argparse
import datetime as dt
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_account_data import KST, Api, album, solve_week  # noqa: E402

COHORTS = ("steady", "normal", "irregular", "late")
REACTIONS = ("NEW_IDEA", "CLEAR_REASON", "DIFFERENT_VIEW", "WANT_MORE")
FEED_SEED = "dm854"
KEY_NS = uuid.UUID("8f1c2b0e-0808-4854-9000-000000000808")  # 같은 대상의 신고는 같은 Idempotency-Key(24시간 재전송 방지)

# 학부모 분석 대화 질문(프리미엄 학부모 한 명당 2~3개)
QUESTIONS = [
    "이번 주에 아이가 가장 자신 있게 푼 생각 유형은 무엇인가요?",
    "되묻기를 받은 뒤 아이 답이 어떻게 달라졌는지 알려 주세요.",
    "아이가 이유를 쓸 때 자주 빠뜨리는 부분이 있나요?",
    "지난주와 비교해 이번 주에 꾸준히 풀었나요?",
    "이번 주 답변 중 가장 길게 생각한 문제는 무엇인가요?",
    "아이가 어려워한 문제를 집에서 어떻게 이야기 나누면 좋을까요?",
]
CORRECTION_COMMENT = "아이가 이유를 함께 썼는데 판정에 반영되지 않은 것 같아요. 다시 확인 부탁드려요. (#808 더미)"
COMMUNITY_REPORT_COMMENT = "친구 글에 문제와 상관없는 내용이 있어요. (#808 더미)"
# (카테고리, 제목, 본문). 제목으로 이미 보낸 문의인지 확인한다
PARENT_INQUIRIES = [
    ("USAGE", "주간 리포트는 언제 나오나요?", "월요일 아침에 확인했는데 지난주 리포트가 언제 만들어지는지 궁금합니다."),
    ("ACCOUNT", "아이 기기를 바꾸면 다시 등록해야 하나요?", "태블릿을 새로 샀는데 기존 기록이 그대로 이어지는지 알고 싶어요."),
    ("PAYMENT", "프리미엄 구독 해지 시점이 궁금합니다", "해지하면 남은 기간 동안은 계속 쓸 수 있는지 알려 주세요."),
    ("USAGE", "형제가 서로 다른 학년이에요", "두 아이 학년이 다른데 각자 다른 테마가 나오는 게 맞나요?"),
    ("USAGE", "되묻기가 너무 어렵다고 해요", "아이가 되묻기 질문을 어려워하는데 도움말을 볼 수 있는 곳이 있을까요?"),
    ("ACCOUNT", "PIN을 잊어버렸어요", "아이가 PIN을 잊어버렸는데 학부모 화면에서 다시 정할 수 있나요?"),
]
STUDENT_INQUIRIES = [
    ("USAGE", "친구 방은 어떻게 꾸며요?", "친구 방처럼 내 방에도 소품을 놓고 싶어요."),
    ("USAGE", "포인트는 어디에 써요?", "포인트가 모였는데 무엇을 살 수 있는지 궁금해요."),
]
INQUIRY_ANSWERS = {
    "주간 리포트는 언제 나오나요?": "주간 리포트는 매주 월요일 0시에 지난주 기록으로 만들어집니다. 알림으로도 알려 드려요.",
    "아이 기기를 바꾸면 다시 등록해야 하나요?": "새 기기에서 연결 코드로 다시 등록하시면 기존 기록은 그대로 이어집니다.",
    "친구 방은 어떻게 꾸며요?": "내 방에서 소품을 사고 원하는 자리에 놓을 수 있어요. 포인트가 필요해요.",
    "PIN을 잊어버렸어요": "학부모 화면의 자녀 설정에서 PIN을 새로 정할 수 있습니다.",
}
INQUIRIES_TO_ANSWER = 4
CORRECTIONS_TO_RESOLVE = 2
# (대상 역할, 제목, 본문)
NOTICES = [
    ("STUDENT", "이번 주 테마가 새로 열렸어요", "월요일부터 금요일까지 하루 한 문제씩 이야기를 따라가 보세요."),
    ("PARENT", "주간 리포트 안내", "주간 리포트는 매주 월요일 0시에 지난주 기록으로 만들어집니다."),
    ("ADMIN", "시연 기간 운영 점검 안내", "12/7 시연 전까지 작업 상태와 AI 사용량을 매일 확인해 주세요."),
]


def load(args):
    """가족 목록과 비밀 파일을 읽어 대상 학생 목록을 만든다. seed(학년 안 순번)는 --count와 관계없이 전체 목록 기준"""
    data = json.loads(Path(args.families).read_text(encoding="utf-8"))
    accounts = {}
    if getattr(args, "secrets", None):
        accounts = {a["loginId"]: a for a in json.loads(Path(args.secrets).read_text(encoding="utf-8"))["accounts"]}
    grades = {int(g.strip().lstrip("Gg")) for g in args.grades.split(",")} if args.grades else None
    chosen = {f["loginId"] for f in data["families"][:args.count]}
    seq, students = {}, []
    for f in data["families"]:
        for c in f["children"]:
            seed = seq.get(c["grade"], 0)
            seq[c["grade"]] = seed + 1
            if f["loginId"] in chosen and (grades is None or c["grade"] in grades):
                students.append({**c, "loginId": f["loginId"], "seed": seed})
    return data, students, accounts


def creds(accounts, st):
    a = accounts.get(st["loginId"])
    if not a or not a.get("password"):
        raise SystemExit(f"{st['loginId']}: 비밀 파일에 없음. 먼저 prepare_accounts.py --families로 계정을 만든다")
    return a["loginId"], a["password"]


def each(students, label, fn):
    """학생마다 fn을 부르고, 실패한 학생은 건너뛰고 끝에 모아 알린다(같은 명령을 다시 돌리면 끝난 것은 건너뜀)"""
    failed = []
    for st in students:
        try:
            fn(st)
        except SystemExit as e:
            print(f"  {st['nickname']}: {e}", file=sys.stderr)
            failed.append(st["nickname"])
    if failed:
        raise SystemExit(f"{label} 실패 {len(failed)}명: {', '.join(failed)}. 같은 명령을 다시 실행")


def cmd_plan(_api, args):
    """API 없이 무리·학년·주별 문제 수와 구독 SQL 값을 보여 준다(계획 9.7.6.2 표와 대조)"""
    data, students, _ = load(args)
    weeks = data["weekStarts"]
    print(f"학생 {len(students)}명, 가족 {len({s['loginId'] for s in students})}개")
    print("무리\t인원\t" + "\t".join(weeks) + "\t합계")
    totals = [0] * len(weeks)
    for cohort in COHORTS:
        n = sum(s["cohort"] == cohort for s in students)
        counts = data["cohorts"][cohort]
        totals = [t + n * c for t, c in zip(totals, counts)]
        print(f"{cohort}\t{n}\t" + "\t".join(str(n * c) for c in counts) + f"\t{n * sum(counts)}")
    print("합\t\t" + "\t".join(map(str, totals)) + f"\t{sum(totals)}")
    for g in sorted({s["grade"] for s in students}):
        gs = [s for s in students if s["grade"] == g]
        print(f"G{g}: {len(gs)}명 " + " ".join(f"{c} {sum(s['cohort'] == c for s in gs)}" for c in COHORTS)
              + f" | 프리미엄 {sum(s['premium'] for s in gs)} 공개 {sum(s['public'] for s in gs)}")
    premium = [s["nickname"] for s in students if s["premium"]]
    print(f"프리미엄 {len(premium)}명(구독 SQL -v premium): {','.join(premium)}")


def community_consent(api, ptok, child_id):
    """학부모가 자녀 COMMUNITY 동의를 저장한다(선택 동의, 같은 값 재전송은 바뀌지 않음)"""
    _, docs, _ = api.call("GET", "/consent-documents")
    doc = next((d for d in docs["items"] if d["kind"] == "COMMUNITY"), None)
    if not doc:
        raise SystemExit("COMMUNITY 동의 문서 없음")
    s, p, _ = api.call("POST", "/me/consents", {"childId": child_id, "consents": [
        {"documentId": doc["documentId"], "version": doc["version"], "agreed": True}]}, ptok)
    api.ok("COMMUNITY 동의", s, p, (200, 201, 204))


def cmd_community(api, args):
    """첫 풀이 전에: 원문 공개를 켜고 공개 대상은 커뮤니티 공개를 켠다. 공유물은 돌아보기 저장 때만 생긴다"""
    _, students, accounts = load(args)

    def turn_on(stok, label, public):
        s, p, _ = api.call("PUT", "/students/me/sharing-preferences", {"parentSharingEnabled": True}, stok)
        api.ok("원문 공개", s, p)
        if public:
            s, p, _ = api.call("PUT", "/students/me/community-settings", {"enabled": True}, stok)
            api.ok("커뮤니티 공개", s, p, (200,))
        print(f"{label}: 원문 공개, 커뮤니티 공개 {'켬' if public else '끔(그대로)'}")

    each(students, "공개 설정", lambda st: turn_on(api.student(st["nickname"], creds(accounts, st))[0],
                                              st["nickname"], st["public"]))
    for nickname in args.demo_child or []:
        # #624 시연 학생: children 명령은 GUARDIAN 동의만 저장하므로 COMMUNITY 동의를 먼저 더한다
        ptok, _ = api.parent()
        child = api.children(ptok).get(nickname)
        if not child:
            raise SystemExit(f"시연 자녀 '{nickname}' 없음")
        community_consent(api, ptok, child["id"])
        turn_on(api.student(nickname)[0], nickname, True)


def cmd_solve(api, args):
    """서버 시계 기준 이번 주를 무리별 문제 수만큼 푼다. wed: 5문제 주인 학생만 월~수 3개, sat: 목표까지 풀고 5문제면 정답 고르기·종료 이야기"""
    data, students, accounts = load(args)

    def solve(st):
        stok, _ = api.student(st["nickname"], creds(accounts, st))
        s, theme, _ = api.call("GET", "/students/me/weekly-theme", token=stok)
        week = api.ok("이번 주 테마", s, theme, (200,))["weekStart"]
        if week not in data["weekStarts"]:
            raise SystemExit(f"{week} 주는 가족 목록 기간 밖")
        target = data["cohorts"][st["cohort"]][data["weekStarts"].index(week)]
        limit = (3 if target == 5 else 0) if args.stage == "wed" else target
        if limit == 0:
            print(f"{st['nickname']}: {week} 주 {st['cohort']} 목표 {target}, 이번 정지점은 건너뜀")
            return
        solve_week(api, stok, st["nickname"], limit=limit, finish=args.stage == "sat" and target == 5, seed=st["seed"])

    each(students, "풀이", solve)


def finished_days(api, stok):
    s, theme, _ = api.call("GET", "/students/me/weekly-theme", token=stok)
    theme = api.ok("이번 주 테마", s, theme, (200,))
    return [d for d in theme["days"] if d.get("attemptStatus") == "COMPLETED"]


def feed(api, stok, mission_id):
    """같은 미션 공유물(본인·신고 숨김 제외). 아직 열람할 수 없으면(마무리 전·엔딩 전) 빈 목록"""
    s, p, _ = api.call("GET", f"/missions/{mission_id}/community-posts?seed={FEED_SEED}&page=0&size=20", token=stok)
    if s == 403:
        return []
    return api.ok("친구 생각", s, p, (200,))["items"]


def cmd_react(api, args):
    """정지점 풀이가 모두 끝난 뒤: 이번 주 끝낸 미션마다 남의 글 최대 N개에 반응한다(반응 API는 멱등)"""
    _, students, accounts = load(args)
    total = [0, 0]

    def react(st):
        stok, _ = api.student(st["nickname"], creds(accounts, st))
        for d in finished_days(api, stok):
            for i, post in enumerate(feed(api, stok, d["missionId"])[:args.per_mission]):
                if post.get("myReactions"):
                    total[1] += 1
                    continue
                kind = REACTIONS[(st["seed"] + i + len(d["day"])) % len(REACTIONS)]
                s, p, _ = api.call("PUT", f"/community-posts/{post['postId']}/reactions/{kind}", token=stok)
                api.ok("반응", s, p, (204,))
                total[0] += 1

    each(students, "반응", react)
    print(f"반응 새로 {total[0]}개, 이미 있음 {total[1]}개")


def cmd_room(api, args):
    """친구 방: G3·G5 공개 학생(꾸준 먼저) 학년별 N명에게 추억의 벽·가구 착용·소품 구매·배치. 가구·소품 코드는 판매 중인 것만"""
    _, students, accounts = load(args)
    order = {c: i for i, c in enumerate(COHORTS)}
    targets = []
    for g in (3, 5):
        gs = sorted((s for s in students if s["grade"] == g and s["public"]), key=lambda s: order[s["cohort"]])
        targets += gs[:args.per_grade]
    furniture = [c for c in (args.furniture or "").split(",") if c]
    decor = [c for c in (args.decor or "").split(",") if c]

    def decorate(st):
        stok, _ = api.student(st["nickname"], creds(accounts, st))
        frames = album(api, stok)
        if frames:
            slots = [{"slotNo": n + 1, "themeId": f["themeId"], "weekStart": f["weekStart"]} for n, f in enumerate(frames[:6])]
            s, p, _ = api.call("PUT", "/students/me/room/frame-slots", {"slots": slots}, stok)
            api.ok("추억의 벽", s, p, (200,))
        s, items, _ = api.call("GET", "/students/me/look-items", token=stok)
        items = {x["itemKey"]: x for x in api.ok("아이템 목록", s, items, (200,))["items"]}
        equip = {}
        for code in furniture:
            if code not in items:
                raise SystemExit(f"가구 {code} 없음")
            if not items[code]["unlocked"]:
                s, p, _ = api.call("POST", f"/students/me/look-items/{code}/unlock", {}, stok,
                                   headers={"Idempotency-Key": str(uuid.uuid4())})
                api.ok(f"{code} 해금(잔액 부족이면 409)", s, p, (200,))
            equip[items[code]["slot"]] = code
        if equip:
            s, look, _ = api.call("GET", "/students/me/preferences", token=stok)
            look = api.ok("꾸미기 조회", s, look, (200,))
            s, p, _ = api.call("PUT", "/students/me/preferences",
                               {"theme": look["theme"], "companion": look["companion"], "equipped": equip}, stok)
            api.ok("가구 착용", s, p, (200,))
        for code in decor:
            if code not in items:
                raise SystemExit(f"소품 {code} 없음")
            if not items[code].get("ownedCount"):
                # 소품 구매는 키가 다르면 또 산다. 보유 수가 0일 때만 산다
                s, p, _ = api.call("POST", f"/students/me/look-items/{code}/purchase", {}, stok,
                                   headers={"Idempotency-Key": str(uuid.uuid4())})
                api.ok(f"{code} 구매(잔액 부족이면 409)", s, p, (200,))
        if decor:
            spots = [{"surface": "FLOOR", "col": 3 + 4 * i, "row": 8, "itemKey": code} for i, code in enumerate(decor)]
            s, p, _ = api.call("PUT", "/students/me/room/decor-spots", {"spots": spots}, stok)
            api.ok("소품 배치", s, p, (200,))
        print(f"{st['nickname']}: 액자 {len(frames)}개, 가구 {sorted(equip)}, 소품 {len(decor)}개 배치")

    each(targets, "방 꾸미기", decorate)


def sse_done(api, label, status, stream):
    if status != 200 or "event:result" not in stream.replace(" ", ""):
        raise SystemExit(f"{label}: 결과 이벤트 없음(HTTP {status})")


def cmd_converse(api, args):
    """프리미엄 학부모 N명이 분석 대화 1개씩, 질문 2~3개. 이미 대화가 있는 자녀는 건너뜀"""
    _, students, accounts = load(args)
    seen, targets = set(), []
    for st in students:
        if st["premium"] and st["loginId"] not in seen:
            seen.add(st["loginId"])
            targets.append(st)
    targets = targets[:args.parents]

    def converse(st):
        idx = targets.index(st)
        ptok, _ = api.parent(creds(accounts, st))
        child = api.children(ptok)[st["nickname"]]
        s, page, _ = api.call("GET", f"/conversations?childId={child['id']}", token=ptok)
        if api.ok("대화 목록", s, page, (200,))["items"]:
            print(f"{st['loginId']}: 대화 이미 있음")
            return
        s, conv, _ = api.call("POST", "/conversations", {"childId": child["id"]}, ptok)
        conv = api.ok("대화 생성", s, conv, (201,))
        asked = [QUESTIONS[(idx + n) % len(QUESTIONS)] for n in range(2 + idx % 2)]
        for q in asked:
            s, stream, _ = api.call("POST", f"/conversations/{conv['conversationId']}/messages", {"question": q}, ptok,
                                    headers={"Accept": "text/event-stream"}, raw=True, timeout=300)
            sse_done(api, "분석 질문", s, stream)
        print(f"{st['loginId']}: 대화 1개, 질문 {len(asked)}개")

    each(targets, "분석 대화", converse)


def my_reports(api, tok):
    s, p, _ = api.call("GET", "/error-reports?page=0&size=100", token=tok)
    return api.ok("신고 목록", s, p, (200,))["items"]


def latest_judgment(api, ptok, child_id, since):
    """자녀 기록 중 판정이 있는 답변 하나(학부모 기록 상세의 answers[].feedback.judgment)"""
    today = dt.datetime.now(KST).date().isoformat()
    s, page, _ = api.call("GET", f"/children/{child_id}/attempts?from={since}&to={today}&page=0&size=20", token=ptok)
    for item in api.ok("학습 기록", s, page, (200,)).get("items") or []:
        s, detail, _ = api.call("GET", f"/children/{child_id}/attempts/{item['attemptId']}", token=ptok)
        for ans in (api.ok("기록 상세", s, detail, (200,)).get("answers") or []):
            judgment = ((ans.get("feedback") or {}).get("judgment") or {})
            if judgment.get("judgmentId"):
                return judgment["judgmentId"]
    return None


def cmd_support(api, args):
    """학부모 정정 요청 N건(WRONG_JUDGMENT), G4·G6 학생 커뮤니티 신고(신고하면 바로 숨겨지므로 시연 학생 학년은 피함), 문의.
    신고·문의 API는 멱등이 아니라 각자 기존 목록에서 같은 대상·제목을 확인한 뒤 건너뜀"""
    data, students, accounts = load(args)
    since = data["weekStarts"][0]
    parents, seen = [], set()
    for st in students:
        if st["loginId"] not in seen:
            seen.add(st["loginId"])
            parents.append(st)

    corrections = [0]

    def correction(st):
        if corrections[0] >= args.corrections:
            return
        ptok, _ = api.parent(creds(accounts, st))
        if any(r["targetType"] == "JUDGMENT" and r["category"] == "WRONG_JUDGMENT" for r in my_reports(api, ptok)):
            corrections[0] += 1
            print(f"{st['loginId']}: 정정 요청 이미 있음")
            return
        child = api.children(ptok)[st["nickname"]]
        judgment = latest_judgment(api, ptok, child["id"], since)
        if not judgment:
            print(f"{st['loginId']}: 판정 있는 기록 없음, 건너뜀")
            return
        s, p, _ = api.call("POST", "/error-reports", {"targetType": "JUDGMENT", "targetId": judgment,
                                                      "category": "WRONG_JUDGMENT", "comment": CORRECTION_COMMENT,
                                                      "studentId": child["id"]}, ptok,
                           headers={"Idempotency-Key": str(uuid.uuid5(KEY_NS, f"correction:{judgment}"))})
        api.ok("정정 요청", s, p, (200, 201))
        corrections[0] += 1
        print(f"{st['loginId']}: 정정 요청 1건")

    each(parents, "정정 요청", correction)

    dummy_names = {s["nickname"] for s in students if s["grade"] in (4, 6)}
    for g in (4, 6):
        reporters = [s for s in students if s["grade"] == g and not s["public"]] or [s for s in students if s["grade"] == g]
        done = False
        for st in reporters:
            stok, _ = api.student(st["nickname"], creds(accounts, st))
            if any(r["targetType"] == "COMMUNITY_POST" for r in my_reports(api, stok)):
                print(f"G{g} {st['nickname']}: 커뮤니티 신고 이미 있음")
                done = True
                break
            post = next((p for d in finished_days(api, stok) for p in feed(api, stok, d["missionId"])
                         if p["author"]["nickname"] in dummy_names), None)
            if not post:
                continue
            s, p, _ = api.call("POST", "/error-reports", {"targetType": "COMMUNITY_POST", "targetId": post["postId"],
                                                          "category": "INAPPROPRIATE", "comment": COMMUNITY_REPORT_COMMENT},
                               stok, headers={"Idempotency-Key": str(uuid.uuid5(KEY_NS, f"post:{post['postId']}"))})
            api.ok("커뮤니티 신고", s, p, (200, 201))
            print(f"G{g} {st['nickname']}: 커뮤니티 신고 1건(공유물은 처리 전까지 숨김)")
            done = True
            break
        if not done:
            print(f"G{g}: 신고할 더미 공유물 없음", file=sys.stderr)

    def inquire(tok, label, items):
        s, page, _ = api.call("GET", "/inquiries?page=0&size=100", token=tok)
        have = {i["title"] for i in api.ok("문의 목록", s, page, (200,))["items"]}
        for category, title, body in items:
            if title in have:
                continue
            s, p, _ = api.call("POST", "/inquiries", {"category": category, "title": title, "body": body}, tok)
            api.ok("문의", s, p, (201,))
        print(f"{label}: 문의 {len(items)}건 확인")

    for st, item in zip(parents, PARENT_INQUIRIES):
        inquire(api.parent(creds(accounts, st))[0], st["loginId"], [item])
    kids = [next((s for s in students if s["grade"] == g), None) for g in (3, 5)]
    for st, item in zip([k for k in kids if k], STUDENT_INQUIRIES):
        inquire(api.student(st["nickname"], creds(accounts, st))[0], st["nickname"], [item])


def admin_items(api, atok, path):
    s, p, _ = api.call("GET", f"{path}?page=0&size=100", token=atok)
    return api.ok(path, s, p, (200,))["items"]


def cmd_admin_ops(api, args):
    """관리자 처리(12/6): 공지 3건, 더미 문의 4건 답변, 더미 정정 요청 2건 검토 → 처리 완료. 이미 된 것은 건너뜀"""
    atok = api.ops_admin()
    titles = {n["title"] for n in admin_items(api, atok, "/admin/notices")}
    now = dt.datetime.now(KST).replace(microsecond=0).isoformat()
    for role, title, body in NOTICES:
        if title in titles:
            continue
        s, p, _ = api.call("POST", "/admin/notices", {"kind": "NOTICE", "title": title, "body": body,
                                                      "targetRoles": [role], "visibleFrom": now}, atok)
        api.ok("공지", s, p, (201,))
    print(f"공지 {len(NOTICES)}건 확인")

    ours = [i for i in admin_items(api, atok, "/admin/inquiries") if i["title"] in INQUIRY_ANSWERS]
    answered = sum(i["status"] == "RESOLVED" for i in ours)
    for i in ours:
        if answered >= INQUIRIES_TO_ANSWER:
            break
        if i["status"] == "RESOLVED":
            continue
        s, p, _ = api.call("POST", f"/admin/inquiries/{i['inquiryId']}/answer", {"answer": INQUIRY_ANSWERS[i["title"]]}, atok)
        api.ok("문의 답변", s, p, (200,))
        answered += 1
    print(f"답변 대상 더미 문의 {len(ours)}건 중 답변 {answered}건")

    ours = [r for r in admin_items(api, atok, "/admin/error-reports")
            if r["targetType"] == "JUDGMENT" and r.get("comment") == CORRECTION_COMMENT]
    resolved = sum(r["status"] == "RESOLVED" for r in ours)
    for r in ours:
        if resolved >= CORRECTIONS_TO_RESOLVE:
            break
        if r["status"] == "RESOLVED":
            continue
        for status in (["IN_REVIEW"] if r["status"] == "RECEIVED" else []) + ["RESOLVED"]:
            s, p, _ = api.call("PATCH", f"/admin/error-reports/{r['reportId']}",
                               {"status": status, "reviewReason": "답변과 기준표를 다시 확인했습니다. (#808 더미)"}, atok)
            api.ok(f"신고 {status}", s, p, (200,))
        resolved += 1
    print(f"더미 정정 요청 {len(ours)}건 중 처리 완료 {resolved}건")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--families", default=str(Path(__file__).resolve().parent / "dummy854-families.json"))
    ap.add_argument("--secrets", help="prepare_accounts.py --families 비밀 파일(저장소 밖)")
    ap.add_argument("--count", type=int, help="앞 N가족만(kind 리허설 6)")
    ap.add_argument("--grades", help="대상 학년, 예: G3,G5(테마가 게시된 학년만 돌릴 때)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="무리·학년·주별 문제 수와 구독 SQL 값(API 없음)")
    p = sub.add_parser("community", help="원문 공개·커뮤니티 공개 켬(첫 풀이 전)")
    p.add_argument("--demo-child", action="append", help="함께 공개할 #624 시연 자녀 별명(시연 학부모 환경 변수)")
    p = sub.add_parser("solve", help="무리별 문제 수만큼 이번 주 풀이")
    p.add_argument("--stage", required=True, choices=("wed", "sat"))
    p = sub.add_parser("react", help="이번 주 끝낸 미션의 남의 글에 반응")
    p.add_argument("--per-mission", type=int, default=3)
    p = sub.add_parser("room", help="친구 방: 추억의 벽·가구·소품")
    p.add_argument("--per-grade", type=int, default=3)
    p.add_argument("--furniture", help="해금·착용할 가구 코드, 쉼표 구분")
    p.add_argument("--decor", help="구매·배치할 소품(DECOR) 코드 2개, 쉼표 구분")
    p = sub.add_parser("converse", help="프리미엄 학부모 분석 대화")
    p.add_argument("--parents", type=int, default=6)
    p = sub.add_parser("support", help="정정 요청·커뮤니티 신고·문의")
    p.add_argument("--corrections", type=int, default=4)
    sub.add_parser("admin-ops", help="공지·문의 답변·정정 요청 처리(운영 관리자)")
    args = ap.parse_args()
    api = None if args.cmd == "plan" else Api()
    {"plan": cmd_plan, "community": cmd_community, "solve": cmd_solve, "react": cmd_react, "room": cmd_room,
     "converse": cmd_converse, "support": cmd_support, "admin-ops": cmd_admin_ops}[args.cmd](api, args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
