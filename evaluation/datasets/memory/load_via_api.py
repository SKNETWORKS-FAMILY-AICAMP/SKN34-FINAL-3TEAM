"""추억 검색 평가셋 memory@1(#568)·memory@2(#853) 적재: 가상 학생 기록을 공개 API로 만든다. SQL INSERT 없음.

#624 시연 계정 스크립트(infrastructure/aws/demo_account_data.py)의 Api(로그인·호출)를 그대로 쓰고,
답은 TOPICS 대신 이 폴더의 students.json에서 넣는다. 순서와 시계 옮기기는 README "만드는 순서"를 따른다.

    python -I load_via_api.py parent-signup            # (PC compose 스택만) 평가 학부모 4명 가입
    python -I load_via_api.py children                 # 학부모마다 가상 자녀(초3·초5 짝, d는 삭제용 하나 더) 모두 9명
    (core_db) prepare-demo-account-students.sql을 초3·초5 짝마다 실행  # is_demo 표시, 초5 시험 구독(EXTRA용)
    python -I load_via_api.py themes                   # 자체 테마 14개 작성·검토 요청·게시
    (core·learning 시계를 그 주 토요일 14:00 KST로) python -I load_via_api.py solve --week W1   # W1~W7 차례로
    (시계 되돌린 뒤) python -I load_via_api.py extra / current / delete
    python -I load_via_api.py manifest                 # 적재 표 확인
    memory@2(#853)는 --dataset ../memory@2를 붙이고 themes 앞에 missions(주마다 새 미션 5개 작성·게시), solve는 W01~W52
    (weeks 명령이 주 키와 시계를 옮길 토요일을 찍음). extra·current·delete는 없음. 순서는 memory@2/README.md

환경 변수는 demo_account_data.py와 같다(DEMO_API_BASE·DEMO_PARENT_*·DEMO_ADMIN_* 등, 값은 출력하지 않음).
학부모는 평가 전용 계정을 쓴다(시연 학부모와 섞지 않음). 학부모 1명당 자녀가 3명까지라(core MAX_CHILDREN)
students.json의 parent 칸(a~d)마다 계정을 나눈다: 로그인 ID = DEMO_PARENT_LOGIN + parent(예: evalparent → evalparenta),
비밀번호는 모두 DEMO_PARENT_PASSWORD. 학부모 로그인 ID는 영문 소문자·숫자 4~30자(하이픈 안 됨).
적재 표(--manifest, 기본 ../../results/memory/load-manifest.json)에는 학생·테마·시도 ID와 주·요일·맥락만 남고
답·질문 원문·토큰은 없다. 환경마다 값이 달라 커밋하지 않는다. 러너가 범위 위반을 이 표로 판정한다.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import uuid

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "infrastructure" / "aws"))
import demo_account_data as demo  # Api·DAYS 재사용

TEXT_TYPES = {"NARRATIVE"}
DATASET, DATA_NAME = HERE, "memory@1"  # main에서 --dataset으로 바꿈


def load(name):
    return json.loads((DATASET / name).read_text(encoding="utf-8"))


def student_rounds(data, s):
    """학생 회차 목록. memory@1은 students.json의 rounds, memory@2는 최근 weekCount주를 주별 미션 답(변형 A·B)으로 만든다."""
    if "rounds" in s:
        return s["rounds"]
    return [{"week": wk, "themeKey": f"T{wk[1:]}", "complete": True, "days": list(demo.DAYS),
             "answers": {d: data["weekMissions"][wk][d]["answers"][s["variant"]] for d in demo.DAYS}}
            for wk in list(data["weeks"])[-s["weekCount"]:]]


def mission_id(data, man, grade, week, day):
    """그 주·요일 미션 ID. memory@1은 학년 표(시드 미션 고정), memory@2는 missions 명령이 만든 주별 미션(적재 표)."""
    if "weekMissions" in data:
        mid = man.data.get("missions", {}).get(week, {}).get(day)
        if not mid:
            raise SystemExit(f"{week} {day} 미션이 적재 표에 없음 — 먼저 missions 명령")
        return mid
    return data["missions"][f"G{grade}"][day]["missionId"]


class Manifest:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {
            "dataset": DATA_NAME, "students": {}, "themes": {}, "attempts": []}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def add_attempt(self, **row):
        rows = self.data["attempts"]
        key = lambda r: (r["studentKey"], r["week"], r["day"], r["context"])
        old = next((r for r in rows if key(r) == key(row)), None)
        if old is None:
            rows.append(row)
        elif row["attemptId"]:
            old.update(row)
        self.save()


def body_for(answer, input_type):
    """students.json 답 → 답변 제출 본문(api-spec 3.1)."""
    if input_type == "NARRATIVE" and "text" in answer:
        part = {"text": answer["text"]}
    elif input_type == "ESSAY" and "essay" in answer:
        part = {"essay": answer["essay"]}
    elif input_type == "SOLUTION_STEPS" and "steps" in answer:
        part = {"finalAnswer": answer["finalAnswer"], "steps": answer["steps"]}
    elif input_type in ("CHOICE", "ORDERING") and "choiceIds" in answer:
        part = {"choiceIds": answer["choiceIds"]}
    else:
        raise SystemExit(f"답 모양이 입력 방식 {input_type}와 맞지 않음")
    return {"inputType": input_type, **part, "dictatedByGuardian": False}


def finish_attempt(api, stok, mission_id, context, answer, label):
    """시작 → 답변 → 피드백(SSE) → 마무리 → 돌아보기. 진행 중 시도는 이어서 끝낸다. 시도 ID를 돌려준다."""
    s, att, _ = api.call("POST", f"/missions/{mission_id}/attempts", {"context": context}, stok)
    api.ok(f"{label} 시작", s, att, (200, 201))
    # 진행 중 시도가 있으면 learning은 맥락과 상관없이 그 시도를 돌려준다(AttemptService.start findInProgress).
    # EXTRA를 시작했는데 테마 시도(themeScene 있음)가 오면 테마 기록을 EXTRA로 잘못 끝내게 되므로 멈춘다
    if context == "EXTRA" and att.get("themeScene"):
        raise SystemExit(f"{label}: 같은 미션의 테마 시도가 진행 중이라 EXTRA를 시작할 수 없음 — 그 시도부터 정리")
    aid = att["attemptId"]
    answers = att.get("answers") or []
    if answers:
        answer_id = answers[-1]["answerId"]
    else:
        _, mission, _ = api.call("GET", f"/missions/{mission_id}", token=stok)
        s, a, _ = api.call("POST", f"/attempts/{aid}/answers", body_for(answer, mission.get("inputType", "NARRATIVE")),
                           stok, headers={"Idempotency-Key": str(uuid.uuid4())})
        answer_id = api.ok(f"{label} 답변", s, a, (200, 201))["answerId"]
    s, stream, _ = api.call("POST", f"/answers/{answer_id}/feedback", token=stok,
                            headers={"Accept": "text/event-stream"}, raw=True, timeout=300)
    if s != 200 or not re.search(r'"status": ?"DONE"', stream):
        raise SystemExit(f"{label} 피드백이 DONE이 아님(HTTP {s})")
    s, p, _ = api.call("POST", f"/attempts/{aid}/finish", {}, stok)
    api.ok(f"{label} 마무리", s, p)
    s, p, _ = api.call("POST", f"/attempts/{aid}/reflection", {"difficulty": "NORMAL"}, stok)
    api.ok(f"{label} 돌아보기", s, p, (200, 201, 204, 409))
    return aid


class EvalApi(demo.Api):
    """demo.Api에서 학부모만 바꿔 쓴다. current가 가리키는 학부모로 로그인하고, student()는 자녀의 학부모를 찾아 들어간다."""

    def __init__(self, data):
        super().__init__()
        self.prefix = os.environ["DEMO_PARENT_LOGIN"]
        self.password = os.environ["DEMO_PARENT_PASSWORD"]
        self.parent_of = {s["nickname"]: s["parent"] for s in data["students"]}
        self.current = None

    def login_id(self, key):
        login = f"{self.prefix}{key}"
        if not re.fullmatch(r"[a-z0-9]{4,30}", login):
            raise SystemExit(f"학부모 로그인 ID '{login}'가 규칙(영문 소문자·숫자 4~30자)에 맞지 않음 — DEMO_PARENT_LOGIN 확인")
        return login

    def parent(self, key=None):
        key = key or self.current
        if key is None:
            raise SystemExit("학부모가 정해지지 않음")
        s, p, ck = self.call("POST", "/auth/parent/login", {"loginId": self.login_id(key), "password": self.password})
        self.ok(f"학부모 {key} 로그인", s, p, (200,))
        return p["accessToken"], ck

    def student(self, nickname):
        ptok, ck = self.parent(self.parent_of[nickname])
        child = self.children(ptok).get(nickname)
        if not child:
            raise SystemExit(f"자녀 '{nickname}'이 없음. 먼저 children 명령으로 등록")
        s, p, _ = self.call("POST", "/auth/student-sessions", {"childId": child["id"]}, ptok, ck)
        self.ok("학생 세션", s, p, (200,))
        return p["accessToken"], child


def parents(data):
    out = {}
    for s in data["students"]:
        out.setdefault(s["parent"], []).append(s)
    return out


def weekly_theme(api, stok):
    s, theme, _ = api.call("GET", "/students/me/weekly-theme", token=stok)
    return api.ok("이번 주 테마", s, theme, (200,))


def cmd_parent_signup(api, args, data, man):
    """평가 전용 학부모(ID·비밀번호)를 parent 칸마다 만든다. 이미 있으면 로그인만 확인한다(PC compose 스택용)."""
    for key in sorted(parents(data)):
        login = api.login_id(key)
        s, p, _ = api.call("POST", "/auth/parent/login", {"loginId": login, "password": api.password})
        if s == 200:
            print(f"평가 학부모 {key}: 이미 있음")
            continue
        body = {"loginId": login, "password": api.password, "name": f"평가 학부모 {key.upper()}"}
        s, p, _ = api.call("POST", "/auth/parent/signup", body)
        api.ok(f"학부모 {key} 가입", s, p, (200, 201))
        print(f"평가 학부모 {key}: 가입함")


def cmd_children(api, args, data, man):
    for key, kids in sorted(parents(data).items()):
        api.current = key
        demo.cmd_children(api, argparse.Namespace(child=[f"{s['nickname']}:{s['grade']}" for s in kids]))
        ptok, _ = api.parent()
        have = api.children(ptok)
        for s in kids:
            man.data["students"][s["studentKey"]] = {"studentId": have[s["nickname"]]["id"], "grade": s["grade"],
                                                     "split": s["split"], "parent": key}
        man.save()
    api.current = None
    print(f"자녀 {len(data['students'])}명 적재 표에 기록. 다음: prepare-demo-account-students.sql을 초3·초5 짝마다 실행")


def cmd_themes(api, args, data, man):
    """자체 테마를 작성·검토 요청·게시한다. 같은 제목 테마가 있으면 이어서 게시, 다른 게시 테마가 있으면 멈춘다."""
    atok = api.admin()
    today = dt.datetime.now(demo.KST).date()
    this_monday = (today - dt.timedelta(days=today.isoweekday() - 1)).isoformat()
    last = list(data["weeks"])[-1]
    if this_monday <= data["weeks"][last]:
        raise SystemExit(f"오늘({today})이 {last} 주 안이라 테마를 게시할 수 없음 — {last} 다음 주(월요일) 이후에 실행")
    for t in load("themes.json"):
        grade = f"G{t['grade']}"
        week = this_monday if t["week"] == "CURRENT" else data["weeks"][t["week"]]
        s, p, _ = api.call("GET", f"/admin/weekly-themes?grade={grade}&weekStart={week}&size=100", token=atok)
        items = api.ok("테마 목록", s, p, (200,))["items"]
        mine = next((i for i in items if i["title"] == t["title"]), None)
        other = [i for i in items if i["status"] == "PUBLISHED" and i is not mine]
        if other and t["week"] == "CURRENT":
            print(f"{t['themeKey']} {grade} {week}: 실행 주에 이미 게시 테마가 있어 그것을 씀")
            continue
        if other:
            raise SystemExit(f"{t['themeKey']} {grade} {week}에 다른 게시 테마가 있음 — 중단하거나 다른 주를 쓸지 정하기")
        if mine is None:
            body = {"grade": grade, "weekStart": week, "title": t["title"], "intro": t["intro"],
                    "days": [{"day": d["day"], "missionId": mission_id(data, man, t["grade"], t["week"], d["day"]),
                              "dialogue": d["dialogue"]} for d in t["days"]]}
            s, mine, _ = api.call("POST", "/admin/weekly-themes", body, atok)
            mine = api.ok(f"{t['themeKey']} 작성", s, mine, (200, 201))
        if mine["status"] != "PUBLISHED":
            if not mine.get("reviewRequested"):
                s, p, _ = api.call("POST", f"/admin/weekly-themes/{mine['themeId']}/review-request", {}, atok)
                api.ok(f"{t['themeKey']} 검토 요청", s, p, (200,))
            s, p, _ = api.call("POST", f"/admin/weekly-themes/{mine['themeId']}/publish", {}, atok)
            api.ok(f"{t['themeKey']} 게시", s, p, (200,))
        man.data["themes"][t["themeKey"]] = {"themeId": mine["themeId"], "grade": t["grade"], "week": t["week"],
                                             "weekStart": week}
        man.save()
        print(f"{t['themeKey']} {grade} {week}: 게시됨")


def plain_text(answer):
    """기준표 예시 답용 글(학생 답 변형 A)."""
    if "text" in answer:
        return answer["text"]
    if "essay" in answer:
        e = answer["essay"]
        return " ".join([e["claim"], *e["reasons"], e["rebuttal"]])
    return " ".join(answer["steps"])


def cmd_missions(api, args, data, man):
    """memory@2: 주마다 시드 틀 미션(초5 DEMO-11~15)의 생각 유형·입력 방식·교과·학년·성취기준·기준표 요소를 복사하고
    제목·질문·예시 답(풀이 단계는 정답도)만 그 주 것으로 바꾼 새 미션을 작성 → 기준표 → 검토 요청 → 검토 승인 → 게시한다.
    틀을 복사하므로 테마 게시 검사(다섯 생각 유형·게시·학년)와 미션 게시 필수 칸을 그대로 채운다.
    미션 ID는 작성 직후 적재 표에 남겨, 다시 실행하면 게시 안 된 것만 이어서 끝낸다(중복 작성 없음)."""
    if "weekMissions" not in data:
        raise SystemExit("memory@1은 시드 미션을 그대로 씀(missions 명령 없음)")
    atok = api.admin()
    seeds = {}
    for day, sd in data["seedMissions"]["G5"].items():
        s, m, _ = api.call("GET", f"/admin/missions/{sd['missionId']}", token=atok)
        m = api.ok(f"{sd['code']} 틀", s, m, (200,))
        v = next(x for x in m["versions"] if x["version"] == m["publishedVersion"])
        r = next(x for x in m["rubrics"] if x["version"] == m["publishedRubricVersion"])
        if v["inputType"] != sd["inputType"]:
            raise SystemExit(f"{sd['code']} 입력 방식 {v['inputType']}가 평가셋 틀({sd['inputType']})과 다름")
        seeds[day] = (v, r)
    done = man.data.setdefault("missions", {})
    keep = ("code", "label", "description", "points", "commonErrors", "goodThought", "judgeVerified", "standardCode")
    for wk in data["weeks"]:
        for day in demo.DAYS:
            v, r = seeds[day]
            wm = data["weekMissions"][wk][day]
            label = f"{wk} {day}"
            mid = done.get(wk, {}).get(day)
            if mid:
                s, m, _ = api.call("GET", f"/admin/missions/{mid}", token=atok)
                if api.ok(f"{label} 상세", s, m, (200,))["status"] == "PUBLISHED":
                    continue
            else:
                body = {k: v.get(k) for k in ("subject", "gradeMin", "gradeMax", "thinkingType", "inputType", "achievementLevels")}
                body.update({k: v.get(k) or [] for k in ("achievementStandards", "choices", "categories", "inputTemplate")})
                body.update(title=wm["title"], question=wm["question"], guide=None, sceneUri=None, staticSceneUri=None,
                            answerUnit=wm.get("answerUnit", v.get("answerUnit")), demoOnly=False)
                s, m, _ = api.call("POST", "/admin/missions", body, atok)
                mid = api.ok(f"{label} 작성", s, m, (200, 201))["missionId"]
                done.setdefault(wk, {})[day] = mid
                man.save()
            rubric = {"elements": [{k: e.get(k) for k in keep} for e in r["elements"]],
                      "answerKey": {"finalAnswer": wm["finalAnswer"]} if v["inputType"] == "SOLUTION_STEPS" else r.get("answerKey"),
                      "exampleAnswer": plain_text(wm["answers"]["A"]), "forbiddenTerms": r.get("forbiddenTerms") or [],
                      "hints": r.get("hints") or [], "keywords": [], "essayType": r.get("essayType")}
            s, m, _ = api.call("PUT", f"/admin/missions/{mid}/rubric", rubric, atok)
            m = api.ok(f"{label} 기준표", s, m, (200, 201))
            pin = {"missionVersion": m["currentVersion"], "rubricVersion": m["currentRubricVersion"]}
            s, p, _ = api.call("POST", f"/admin/missions/{mid}/review-request", pin, atok)
            api.ok(f"{label} 검토 요청", s, p, (200,))
            s, p, _ = api.call("POST", f"/admin/missions/{mid}/review",
                               {**pin, "result": "APPROVED", "comment": "#853 평가 전용 합성 미션"}, atok)
            api.ok(f"{label} 검토", s, p, (200,))
            s, p, _ = api.call("POST", f"/admin/missions/{mid}/publish", {}, atok)
            api.ok(f"{label} 게시", s, p, (200,))
        print(f"{wk} {data['weeks'][wk]}: 미션 5개 게시")


def cmd_weeks(api, args, data, man):
    """주 키와 시계를 옮길 그 주 토요일(14:00 KST = 05:00 UTC)을 찍는다. README 반복문이 읽는다."""
    for wk, start in data["weeks"].items():
        print(wk, (dt.date.fromisoformat(start) + dt.timedelta(days=5)).isoformat())


def cmd_solve(api, args, data, man):
    """서버 시계가 --week 주 토요일일 때 학생마다 그 주 회차를 푼다(memory@1 W1~W6 다섯·W7 셋, memory@2 풀이 주마다 다섯)."""
    if args.week not in data["weeks"]:
        raise SystemExit(f"--week {args.week}가 평가셋 주({', '.join(data['weeks'])})에 없음")
    week_start = data["weeks"][args.week]
    for s in data["students"]:
        r = next((x for x in student_rounds(data, s) if x["week"] == args.week), None)
        if r is None or man.data["students"].get(s["studentKey"], {}).get("deleted"):
            continue
        stok, _ = api.student(s["nickname"])
        theme = weekly_theme(api, stok)
        want = man.data["themes"][r["themeKey"]]["themeId"]
        if theme["weekStart"] != week_start or theme["themeId"] != want:
            raise SystemExit(f"{s['studentKey']}: 서버 이번 주 {theme['weekStart']} 테마가 {args.week} {r['themeKey']}가 아님 — 시계 확인")
        days = {d["day"]: d for d in theme["days"]}
        for day in r["days"]:
            d = days[day]
            if d["missionId"] != mission_id(data, man, s["grade"], args.week, day):
                raise SystemExit(f"{s['studentKey']} {args.week} {day} 미션이 평가셋 표와 다름")
            aid = None  # 이미 끝낸 요일(다시 실행)은 요일 응답에 시도 ID가 없어 비워 두고, 러너가 학생·주·미션으로 채움
            if d.get("attemptStatus") != "COMPLETED":
                if d["state"] != "OPEN":
                    raise SystemExit(f"{s['studentKey']} {args.week} {day}가 {d['state']}라 지금 풀 수 없음")
                answer = r["answers"][day] or data["missions"][f"G{s['grade']}"][day]["defaultAnswer"]
                aid = finish_attempt(api, stok, d["missionId"], "THEME_DAY", answer, f"{s['studentKey']} {args.week} {day}")
            man.add_attempt(studentKey=s["studentKey"], week=args.week, day=day, context="THEME_DAY", attemptId=aid,
                            themeKey=r["themeKey"], missionId=d["missionId"], complete=r["complete"])
        print(f"{s['studentKey']} {args.week} {r['themeKey']}: {len(r['days'])}문제 완료")


def cmd_extra(api, args, data, man):
    """실제 시각: 초5 학생이 그 학년 표의 미션을 EXTRA로 한 번 더 푼다(프리미엄 시험 구독 필요)."""
    for s in data["students"]:
        if not s.get("extra"):
            continue
        done = next((r for r in man.data["attempts"] if r["studentKey"] == s["studentKey"] and r["context"] == "EXTRA"
                     and r["attemptId"]), None)
        if done:  # 다시 실행해도 EXTRA 시도를 새로 만들지 않음
            print(f"{s['studentKey']}: EXTRA 이미 있음")
            continue
        stok, _ = api.student(s["nickname"])
        m = data["missions"][f"G{s['grade']}"][s["extra"]["missionDay"]]
        aid = finish_attempt(api, stok, m["missionId"], "EXTRA", s["extra"]["answer"], f"{s['studentKey']} EXTRA")
        man.add_attempt(studentKey=s["studentKey"], week="EXTRA", day=None, context="EXTRA", attemptId=aid,
                        themeKey=None, complete=False)
        print(f"{s['studentKey']}: EXTRA 1문제 완료")


def cmd_current(api, args, data, man):
    """실제 시각: 실행 주 게시 테마에서 열린 서술 요일 1문제를 푼다(진행 주 제외 시험)."""
    for s in data["students"]:
        if not s.get("current"):
            continue
        stok, _ = api.student(s["nickname"])
        theme = weekly_theme(api, stok)
        if theme["weekStart"] <= data["weeks"]["W7"]:
            raise SystemExit("실행 주가 W7 이후가 아님 — 실제 시각인지 확인")
        target = None
        for d in theme["days"]:
            if d["state"] != "OPEN":
                continue
            _, mission, _ = api.call("GET", f"/missions/{d['missionId']}", token=stok)
            if mission.get("inputType") in TEXT_TYPES:
                target = d
                break
        if target is None:
            print(f"{s['studentKey']}: 실행 주에 열린 서술 문제가 없음 — 건너뜀(이 학생 CURRENT 질문은 결과에서 뺌)")
            continue
        aid = target.get("attemptId")
        if target.get("attemptStatus") != "COMPLETED":
            aid = finish_attempt(api, stok, target["missionId"], "THEME_DAY", s["current"]["answer"], f"{s['studentKey']} CURRENT")
        man.add_attempt(studentKey=s["studentKey"], week="CURRENT", day=target["day"], context="THEME_DAY",
                        attemptId=aid, themeKey=None, complete=False, weekStart=theme["weekStart"])
        print(f"{s['studentKey']}: 실행 주 {theme['weekStart']} {target['day']} 1문제 완료")


def cmd_delete(api, args, data, man):
    """deleteAfterLoad 학생의 자녀 프로필을 지운다(비밀번호 재확인 → 삭제 요청). 학생 ID는 적재 표에 남아 있다."""
    password = api.password
    for s in data["students"]:
        if not s["deleteAfterLoad"]:
            continue
        ptok, ck = api.parent(s["parent"])
        child = api.children(ptok).get(s["nickname"])
        if child is None:
            print(f"{s['studentKey']}: 이미 없음")
            continue
        scope = {"purpose": "CHILD_DELETE", "childId": child["id"], "scope": "PROFILE"}
        st, p, _ = api.call("POST", "/me/reauth/password", {**scope, "password": password}, ptok, ck)
        token = api.ok("비밀번호 재확인", st, p, (200, 201))["reauthToken"]
        st, p, _ = api.call("POST", f"/children/{child['id']}/deletion-requests", {"scope": "PROFILE"}, ptok, ck,
                            headers={"X-Reauth-Token": token})
        api.ok(f"{s['studentKey']} 삭제 요청", st, p, (200, 201, 202))
        man.data["students"][s["studentKey"]]["deleted"] = True
        man.save()
        print(f"{s['studentKey']}: 프로필 삭제 요청 HTTP {st}")


def cmd_manifest(api, args, data, man):
    rows = man.data["attempts"]
    by = {}
    for r in rows:
        by.setdefault(r["studentKey"], []).append(r["week"])
    print(f"학생 {len(man.data['students'])} · 테마 {len(man.data['themes'])} · 시도 {len(rows)}")
    for key in sorted(by):
        weeks = by[key]
        print(f"  {key}: " + ", ".join(f"{w}×{weeks.count(w)}" for w in sorted(set(weeks))))


def main():
    global DATASET, DATA_NAME
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(HERE), help="평가셋 폴더(기본 memory@1, memory@2는 ../memory@2)")
    ap.add_argument("--manifest", help="적재 표(기본 memory@1 load-manifest.json, 그 밖 load-manifest__<평가셋>.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("parent-signup", "children", "missions", "themes", "extra", "current", "delete", "manifest", "weeks"):
        sub.add_parser(name)
    p = sub.add_parser("solve")
    p.add_argument("--week", required=True, help="memory@1 W1~W7, memory@2 W01~W52")
    args = ap.parse_args()
    DATASET = pathlib.Path(args.dataset).resolve()
    data = load("students.json")
    DATA_NAME = data["dataset"]
    results = REPO / "evaluation" / "results" / "memory"
    man = Manifest(args.manifest or results / ("load-manifest.json" if DATA_NAME == "memory@1" else f"load-manifest__{DATA_NAME}.json"))
    if man.data["dataset"] != DATA_NAME:
        raise SystemExit(f"적재 표 {man.path.name}는 {man.data['dataset']} 것 — --manifest 확인")
    api = None if args.cmd in ("manifest", "weeks") else EvalApi(data)
    {"parent-signup": cmd_parent_signup, "children": cmd_children, "missions": cmd_missions, "themes": cmd_themes,
     "solve": cmd_solve, "extra": cmd_extra, "current": cmd_current, "delete": cmd_delete, "manifest": cmd_manifest,
     "weeks": cmd_weeks}[args.cmd](api, args, data, man)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
