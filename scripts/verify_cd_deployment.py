"""#186 배포 후 경로 확인: 로그인 → 학습 제출 → 리포트 조회 (NFR-OPS-02).

전용 시연 계정 fixture 파일로 실제 공개 API를 호출한다. 토큰·쿠키·PIN·응답 본문은 결과에 남기지
않는다. 판정(LLM)·결제·환불은 호출하지 않는다. 부모 refresh 쿠키는 사용할 때마다 회전하므로
새 값을 같은 fixture 파일에 바로 다시 쓴다(재사용하면 core가 세션을 폐기한다).

답변을 낼 미션은 학생 미션 목록에서 고른다. 판정을 부르지 않으므로 확인마다 진행 중 시도가 하나
남고, 그 시도에 첫 답변을 다시 내면 learning이 422를 준다. 그래서 fixture missionId가 시작 전이면
그 미션을, 아니면 answer.inputType이 같은 다른 시작 전 미션을 쓴다. 시작 전 미션이 없으면 fixture
미션의 진행 중 시도를 돌려받아 저장된 답변을 조회만 한다(read-answer, 답변 쓰기는 확인하지 않음).

fixture 파일(작업자 PC에만 두고 Git·Actions Secret에 넣지 않음):
{
  "dedicatedDemoFixture": true, "allowAnswerSubmission": true,
  "childId": "<UUID>", "studentPin": "<PIN>", "studentDeviceCookie": "<student_device 값>",
  "missionId": "<공개 시연 미션 UUID>", "answer": {"inputType": "NARRATIVE", "text": "..."},
  "parentRefreshCookie": "<sagomungchi_refresh 값, 최대 7일>"
}
"""

import argparse
import json
import os
import re
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REFRESH_COOKIE = "sagomungchi_refresh"
MAX_BODY = 4 * 1024 * 1024
MISSION_PAGE_SIZE = 100
MAX_MISSION_PAGES = 10
STEP_COUNT = 6


class CheckFailed(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 인증 정보를 다른 주소로 넘기지 않는다


def base_url(value):
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise CheckFailed("기준 주소는 경로 없는 https origin이어야 합니다")
    return value.rstrip("/")


def load_fixture(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        data.get("dedicatedDemoFixture") is not True
        or data.get("allowAnswerSubmission") is not True
    ):
        raise CheckFailed("답변 제출을 허용한 전용 시연 fixture가 필요합니다")
    for field in ("childId", "missionId"):
        uuid.UUID(str(data.get(field)))
    for field in ("studentPin", "studentDeviceCookie", "parentRefreshCookie"):
        value = data.get(field)
        if not isinstance(value, str) or not value or re.search(r"[\r\n;]", value):
            raise CheckFailed(f"fixture 값 형식 오류: {field}")
    if not isinstance(data.get("answer"), dict) or not data["answer"].get("inputType"):
        raise CheckFailed("fixture answer에 inputType이 필요합니다")
    return data


def save_fixture(path, data):
    """회전된 refresh 쿠키를 원자적으로 저장한다. 중간 실패로 기존 값을 잃지 않게 한다."""
    path = Path(path)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".fixture-")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp, path)


def call(
    base, method, path, *, token=None, cookie=None, body=None, headers=None, opener=None
):
    """(상태, JSON 본문, Set-Cookie 목록). 오류 응답 본문은 읽지 않는다."""
    request_headers = {
        "Accept": "application/json",
        "Origin": base,
        "X-Requested-With": "XMLHttpRequest",
        **(headers or {}),
    }
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    if cookie:
        request_headers["Cookie"] = cookie
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        request_headers["Content-Type"] = "application/json"
    request = Request(base + path, data=data, headers=request_headers, method=method)
    try:
        with (opener or build_opener(NoRedirect())).open(
            request, timeout=30
        ) as response:
            if "application/json" not in response.headers.get("Content-Type", ""):
                raise CheckFailed(f"{method} {template(path)}: JSON 응답이 아님")
            payload = response.read(MAX_BODY + 1)
            if len(payload) > MAX_BODY:
                raise CheckFailed(f"{method} {template(path)}: 응답이 너무 큼")
            return (
                response.status,
                json.loads(payload),
                response.headers.get_all("Set-Cookie") or [],
            )
    except HTTPError as exc:
        raise CheckFailed(f"{method} {template(path)}: HTTP {exc.code}") from None
    except URLError as exc:
        raise CheckFailed(
            f"{method} {template(path)}: 연결 실패 {type(exc.reason).__name__}"
        ) from None


def template(path):
    """기록용 경로. ID는 지운다."""
    return re.sub(r"[0-9a-fA-F-]{36}", "{id}", path)


def fresh_mission(missions, preferred, input_type):
    """답변을 낼 시작 전 미션 ID. fixture 미션을 먼저, 없으면 같은 입력 방식의 첫 미션."""
    candidates = [
        str(item.get("id"))
        for item in missions
        if isinstance(item, dict)
        and item.get("status") == "NOT_STARTED"
        and item.get("inputType") == input_type
    ]
    if str(preferred) in candidates:
        return str(preferred)
    return candidates[0] if candidates else None


def rotated_refresh(set_cookies):
    for header in set_cookies:
        name, _, rest = header.partition("=")
        if name.strip() == REFRESH_COOKIE:
            value = rest.split(";", 1)[0]
            if value:
                return value
    raise CheckFailed("refresh 응답에 회전된 쿠키가 없습니다")


def verify(base, fixture_path, opener=None):
    data = load_fixture(fixture_path)
    steps = []

    def step(name, fn):
        started = time.monotonic()
        try:
            result = fn()
        except CheckFailed as exc:
            steps.append({"step": name, "ok": False, "error": str(exc)})
            raise
        steps.append(
            {"step": name, "ok": True, "ms": int((time.monotonic() - started) * 1000)}
        )
        return result

    try:

        def student_login():
            _, body, _ = call(
                base,
                "POST",
                "/api/v1/auth/student/login",
                cookie=f"student_device={data['studentDeviceCookie']}",
                body={"childId": data["childId"], "pin": data["studentPin"]},
                opener=opener,
            )
            if body.get("role") != "STUDENT" or not body.get("accessToken"):
                raise CheckFailed("학생 로그인 응답이 학생 세션이 아님")
            return body["accessToken"]

        student = step("student-login", student_login)

        def pick_mission():
            missions = []
            page = 0
            while True:
                _, body, _ = call(
                    base,
                    "GET",
                    f"/api/v1/missions?page={page}&size={MISSION_PAGE_SIZE}",
                    token=student,
                    opener=opener,
                )
                items = body.get("items")
                if not isinstance(items, list):
                    raise CheckFailed("미션 목록 응답 형식이 아님")
                missions.extend(items)
                page += 1
                if (
                    not items
                    or len(missions) >= int(body.get("totalElements") or 0)
                    or page >= MAX_MISSION_PAGES
                ):
                    break
            fresh = fresh_mission(
                missions, data["missionId"], data["answer"]["inputType"]
            )
            # 시작 전 미션이 없으면 fixture 미션의 진행 중 시도를 읽기만 한다
            return fresh or str(data["missionId"])

        mission = step("pick-mission", pick_mission)

        def start_attempt():
            status, body, _ = call(
                base,
                "POST",
                f"/api/v1/missions/{mission}/attempts",
                token=student,
                body={},
                opener=opener,
            )
            if status not in (200, 201) or not body.get("attemptId"):
                raise CheckFailed("시도 시작 응답에 attemptId가 없음")
            # 201은 새 시도. 200은 진행 중 시도 재사용이며 답변이 있으면 다시 내지 않는다
            answered = status == 200 and bool(body.get("answers"))
            return body["attemptId"], answered

        attempt, answered = step("start-attempt", start_attempt)

        def read_answer():
            _, body, _ = call(
                base,
                "GET",
                f"/api/v1/attempts/{attempt}",
                token=student,
                opener=opener,
            )
            answers = body.get("answers")
            if not isinstance(answers, list) or not any(
                isinstance(a, dict) and a.get("answerId") for a in answers
            ):
                raise CheckFailed("진행 중 시도에서 저장된 답변을 읽지 못함")

        def submit_answer():
            status, body, _ = call(
                base,
                "POST",
                f"/api/v1/attempts/{attempt}/answers",
                token=student,
                body=data["answer"],
                headers={"Idempotency-Key": str(uuid.uuid4())},
                opener=opener,
            )
            if status != 201 or not body.get("answerId"):
                raise CheckFailed("답변 제출이 저장되지 않음")

        if answered:
            step("read-answer", read_answer)
        else:
            step("submit-answer", submit_answer)

        def parent_refresh():
            _, body, cookies = call(
                base,
                "POST",
                "/api/v1/auth/refresh",
                cookie=f"{REFRESH_COOKIE}={data['parentRefreshCookie']}",
                body={},
                opener=opener,
            )
            data["parentRefreshCookie"] = rotated_refresh(cookies)
            save_fixture(
                fixture_path, data
            )  # 회전 즉시 저장. 이후 단계가 실패해도 다음 실행 가능
            if body.get("role") != "PARENT" or not body.get("accessToken"):
                raise CheckFailed("refresh 응답이 학부모 세션이 아님")
            return body["accessToken"]

        parent = step("parent-refresh", parent_refresh)

        def list_reports():
            _, body, _ = call(
                base,
                "GET",
                f"/api/v1/children/{data['childId']}/reports",
                token=parent,
                opener=opener,
            )
            if not isinstance(body.get("items"), list):
                raise CheckFailed("리포트 목록 응답 형식이 아님")

        step("list-reports", list_reports)
    except CheckFailed:
        pass
    return {
        "checkedAt": datetime.now(UTC).isoformat(),
        "ok": len(steps) == STEP_COUNT and all(item["ok"] for item in steps),
        "steps": steps,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(base_url(args.base_url), args.fixture)
    except (CheckFailed, OSError, ValueError) as exc:
        result = {
            "checkedAt": datetime.now(UTC).isoformat(),
            "ok": False,
            "steps": [
                {
                    "step": "fixture",
                    "ok": False,
                    "error": type(exc).__name__
                    if not isinstance(exc, CheckFailed)
                    else str(exc),
                }
            ],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "steps": [
                    s["step"] + (":ok" if s["ok"] else ":fail") for s in result["steps"]
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
