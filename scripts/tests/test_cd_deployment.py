"""#186 배포 실행 게이트·배포 후 경로 확인·이력 기록·workflow 구조. 네트워크·AWS 호출 없음."""

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cd = load("cd_release")
smoke = load("verify_cd_deployment")
record = load("cd_record")

ECR = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/sagomungchi/"
READY_POLICY = {
    "executionEnabled": True,
    "releaseBranch": "main",
    "approvers": ["20220348-kim", "kty2001"],
    "environmentProtectionVerified": True,
    "infrastructureReady": True,
}


def prod_plan(**overrides):
    plan = {
        "environment": "prod",
        "operation": "deploy",
        "sourceCommit": "a" * 40,
        "sourceBranch": "main",
        "services": ["learning-service", "report-service"],
        "currentRelease": "main-1111",
        "targetRelease": "main-2222",
        "reason": "main 릴리스 배포",
        "databaseAction": "none",
        "compatibility": {
            key: {"status": "compatible", "evidence": "release-pr/ci"}
            for key in cd.CHECKS
        },
    }
    plan.update(overrides)
    return plan


def images(*services):
    return {s: f"{ECR}{s}@sha256:" + "d" * 64 for s in services}


class GateTests(unittest.TestCase):
    def test_deploy_may_wait_for_images_but_is_not_executable(self):
        result = cd.validate(prod_plan(), READY_POLICY, pending_images=True)
        self.assertTrue(result["valid"])
        self.assertFalse(result["executable"])
        self.assertIn("배포 이미지 빌드 전", result["blocks"])

    def test_rollback_needs_images_even_before_build(self):
        plan = prod_plan(operation="rollback")
        self.assertFalse(cd.validate(plan, READY_POLICY, pending_images=True)["valid"])

    def test_ready_plan_with_built_images_is_executable(self):
        plan = prod_plan(images=images("learning-service", "report-service"))
        self.assertTrue(cd.validate(plan, READY_POLICY)["executable"])

    def test_images_must_match_services(self):
        plan = prod_plan(images=images("learning-service"))
        self.assertFalse(cd.validate(plan, READY_POLICY)["valid"])

    def test_services_must_be_known_and_unique(self):
        for services in ([], ["web"], ["ai-service", "ai-service"], None):
            with self.subTest(services=services):
                plan = prod_plan(services=services, images=images("ai-service"))
                self.assertFalse(cd.validate(plan, READY_POLICY)["valid"])


class GateCliTests(unittest.TestCase):
    def run_cli(self, root, plan, *extra):
        (root / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        (root / "policy.json").write_text(json.dumps(READY_POLICY), encoding="utf-8")
        run = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/cd_release.py"),
                "--plan",
                str(root / "plan.json"),
                "--policy",
                str(root / "policy.json"),
                "--output",
                str(root / "record.json"),
                *extra,
            ],
            capture_output=True,
            cwd=root,
            check=False,
        )
        return run.returncode, json.loads(
            (root / "record.json").read_text(encoding="utf-8")
        )

    def git(self, root, *args):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def test_images_file_fills_deploy_and_require_executable_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "images.json").write_text(
                json.dumps(images("learning-service", "report-service")),
                encoding="utf-8",
            )
            code, out = self.run_cli(
                root,
                prod_plan(),
                "--images",
                str(root / "images.json"),
                "--require-executable",
            )
            self.assertEqual(code, 0)
            self.assertTrue(out["executable"])
            self.assertEqual(set(out["images"]), {"learning-service", "report-service"})

    def test_require_executable_fails_with_code_3_when_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code, out = self.run_cli(
                root, prod_plan(), "--pending-images", "--require-executable"
            )
            self.assertEqual(code, 3)
            self.assertTrue(out["valid"])

    def test_commit_must_match_running_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = prod_plan(images=images("learning-service", "report-service"))
            code, out = self.run_cli(root, plan, "--expect-commit", "b" * 40)
            self.assertEqual(code, 2)
            self.assertIn(
                "계획의 sourceCommit이 실행 중인 커밋과 다릅니다", out["errors"]
            )

    def test_rollback_keeps_previous_release_commit(self):
        # 롤백은 현재 main에서 실행하지만 계획의 sourceCommit은 되돌릴 이전 릴리스다
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = prod_plan(
                operation="rollback",
                images=images("learning-service", "report-service"),
                previousApproval={"release": "main-2222", "record": "runs/41"},
            )
            code, out = self.run_cli(root, plan, "--expect-commit", "b" * 40)
            self.assertEqual(code, 0)
            self.assertTrue(out["executable"])

    def test_commit_must_be_in_release_branch_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, "init", "-q", "-b", "main")
            self.git(root, "commit", "-q", "--allow-empty", "-m", "release")
            released = self.git(root, "rev-parse", "HEAD")
            self.git(root, "checkout", "-q", "-b", "feature")
            self.git(root, "commit", "-q", "--allow-empty", "-m", "not released")
            unreleased = self.git(root, "rev-parse", "HEAD")
            base = images("learning-service", "report-service")
            ok, _ = self.run_cli(
                root,
                prod_plan(sourceCommit=released, images=base),
                "--require-ancestor-of",
                "main",
            )
            self.assertEqual(ok, 0)
            bad, out = self.run_cli(
                root,
                prod_plan(sourceCommit=unreleased, images=base),
                "--require-ancestor-of",
                "main",
            )
            self.assertEqual(bad, 2)
            self.assertTrue(any("main 이력" in e for e in out["errors"]))


class FakeResponse:
    def __init__(self, status, body, cookies=()):
        self.status = status
        self._body = json.dumps(body).encode()
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        for cookie in cookies:
            self.headers["Set-Cookie"] = cookie

    def read(self, limit=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """경로별 응답. 실패할 경로는 HTTP 상태 코드로 지정한다."""

    def __init__(
        self,
        fail=None,
        rotate=True,
        theme=None,
        start_status=201,
        answers=None,
        input_type="NARRATIVE",
    ):
        self.calls = []
        self.fail = fail or {}
        self.rotate = rotate
        self.theme = WEEKDAY_THEME if theme is None else theme
        self.start_status = start_status
        self.answers = answers or []
        self.input_type = input_type

    def open(self, request, timeout=None):
        path = request.full_url.split("example.test", 1)[1]
        self.calls.append(
            (
                request.get_method(),
                path,
                dict(request.header_items()),
                json.loads(request.data) if request.data else None,
            )
        )
        for key, code in self.fail.items():
            if key in path:
                raise HTTPError(request.full_url, code, "fail", Message(), io.BytesIO())
        if path.endswith("/auth/student/login"):
            return FakeResponse(
                200, {"accessToken": "student-token", "role": "STUDENT"}
            )
        if path == "/api/v1/students/me/weekly-theme":
            return FakeResponse(200, self.theme)
        if path.endswith("/attempts"):
            return FakeResponse(
                self.start_status,
                {
                    "attemptId": ATTEMPT,
                    "answers": self.answers,
                    "mission": {"inputType": self.input_type},
                },
            )
        if path.endswith(f"/attempts/{ATTEMPT}"):
            return FakeResponse(200, {"attemptId": ATTEMPT, "answers": self.answers})
        if path.endswith("/answers"):
            return FakeResponse(201, {"answerId": "a-1"})
        if path.endswith("/auth/refresh"):
            cookies = (
                ["sagomungchi_refresh=rotated-value; Path=/api/v1/auth; HttpOnly"]
                if self.rotate
                else []
            )
            return FakeResponse(
                200, {"accessToken": "parent-token", "role": "PARENT"}, cookies
            )
        if "/reports" in path:
            return FakeResponse(200, {"items": []})
        raise AssertionError(path)


FIXTURE = {
    "dedicatedDemoFixture": True,
    "allowAnswerSubmission": True,
    "childId": "22222222-2222-2222-2222-222222222222",
    "studentPin": "135790",
    "studentDeviceCookie": "device-secret",
    "missionId": "33333333-3333-3333-3333-333333333333",
    "answer": {"inputType": "NARRATIVE", "text": "물이 얼면 부피가 커져서 그래요"},
    "parentRefreshCookie": "old-refresh",
}

ATTEMPT = "11111111-1111-1111-1111-111111111111"
STORED_ANSWER = [{"answerId": "a-0", "inputType": "NARRATIVE"}]
FIXTURE_MISSION = FIXTURE["missionId"]
OTHER_MISSION = "44444444-4444-4444-4444-444444444444"
TODAY_MISSION = "55555555-5555-5555-5555-555555555555"


def theme(today=None, review_open=False, review=()):
    """api-spec 2.11 학생 주간 테마 모양. today가 있으면 그 미션이 오늘 OPEN 요일 문제."""
    days = [
        {
            "day": "MON",
            "missionId": OTHER_MISSION,
            "state": "CLOSED",
            "attemptStatus": "COMPLETED",
        },
    ]
    if today:
        days.append(
            {"day": "TUE", "missionId": today, "state": "OPEN", "attemptStatus": None}
        )
    return {
        "themeId": "66666666-6666-6666-6666-666666666666",
        "days": days,
        "review": {
            "open": review_open,
            "missions": [
                {"missionId": mission, "completed": completed, "missed": not completed}
                for mission, completed in review
            ],
        },
    }


WEEKDAY_THEME = theme(today=TODAY_MISSION)
WEEKEND_THEME = theme(
    review_open=True,
    review=[(OTHER_MISSION, True), (FIXTURE_MISSION, True), (TODAY_MISSION, False)],
)


class SmokeTests(unittest.TestCase):
    def run_smoke(self, opener, fixture=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "fixture.json"
        path.write_text(json.dumps(fixture or FIXTURE), encoding="utf-8")
        result = smoke.verify("https://example.test", path, opener=opener)
        return result, json.loads(path.read_text(encoding="utf-8"))

    def test_full_path_passes_and_persists_rotated_refresh(self):
        opener = FakeOpener()
        result, saved = self.run_smoke(opener)
        self.assertTrue(result["ok"])
        self.assertEqual(
            [s["step"] for s in result["steps"]],
            [
                "student-login",
                "pick-mission",
                "start-attempt",
                "submit-answer",
                "parent-refresh",
                "list-reports",
            ],
        )
        self.assertEqual(saved["parentRefreshCookie"], "rotated-value")
        answer = next(c for c in opener.calls if c[1].endswith("/answers"))
        self.assertIn("Idempotency-key", answer[2])
        self.assertFalse(
            any("/feedback" in c[1] or "/payments" in c[1] for c in opener.calls)
        )

    def test_result_never_contains_credentials(self):
        result, _ = self.run_smoke(FakeOpener())
        text = json.dumps(result)
        for secret in (
            "student-token",
            "parent-token",
            "device-secret",
            "135790",
            "rotated-value",
            "old-refresh",
        ):
            self.assertNotIn(secret, text)

    def test_failure_stops_later_steps_and_hides_ids(self):
        opener = FakeOpener(fail={"/answers": 422})
        result, saved = self.run_smoke(opener)
        self.assertFalse(result["ok"])
        self.assertEqual(result["steps"][-1]["step"], "submit-answer")
        self.assertIn(
            "/api/v1/attempts/{id}/answers: HTTP 422", result["steps"][-1]["error"]
        )
        self.assertFalse(any(c[1].endswith("/auth/refresh") for c in opener.calls))
        self.assertEqual(saved["parentRefreshCookie"], "old-refresh")

    def started(self, opener):
        """(시작한 미션 ID, 시작 본문). context를 빼면 EXTRA라 항상 명시해야 한다."""
        call = next(c for c in opener.calls if c[1].endswith("/attempts"))
        return call[1].split("/")[4], call[3]

    def test_weekday_starts_today_theme_problem_with_theme_day(self):
        opener = FakeOpener()
        result, _ = self.run_smoke(opener)
        self.assertTrue(result["ok"])
        self.assertEqual(
            self.started(opener), (TODAY_MISSION, {"context": "THEME_DAY"})
        )
        self.assertFalse(
            any(c[1].startswith("/api/v1/missions?") for c in opener.calls)
        )

    def test_weekend_review_prefers_fixture_mission_among_completed(self):
        opener = FakeOpener(theme=WEEKEND_THEME)
        result, _ = self.run_smoke(opener)
        self.assertTrue(result["ok"])
        self.assertEqual(
            self.started(opener), (FIXTURE_MISSION, {"context": "THEME_REVIEW"})
        )
        other = FakeOpener(theme=theme(review_open=True, review=[(OTHER_MISSION, True)]))
        self.assertTrue(self.run_smoke(other)[0]["ok"])
        self.assertEqual(
            self.started(other), (OTHER_MISSION, {"context": "THEME_REVIEW"})
        )

    def test_without_open_day_or_completed_review_fails_before_starting(self):
        for value in (
            theme(),
            theme(review_open=True, review=[(TODAY_MISSION, False)]),
            theme(review_open=False, review=[(FIXTURE_MISSION, True)]),
            {"days": None},
        ):
            opener = FakeOpener(theme=value)
            result, _ = self.run_smoke(opener)
            self.assertFalse(result["ok"])
            self.assertEqual(result["steps"][-1]["step"], "pick-mission")
            self.assertFalse(any(c[1].endswith("/attempts") for c in opener.calls))

    def test_start_refusal_is_reported_without_extra_fallback(self):
        # 409(learning 요일·마무리 문제 거부)·429(무료 EXTRA 재활성 때 한도)는 EXTRA로 바꿔 시도하지 않는다
        for code in (409, 429):
            opener = FakeOpener(fail={"/attempts": code})
            result, _ = self.run_smoke(opener)
            self.assertFalse(result["ok"])
            self.assertIn(
                f"/api/v1/missions/{{id}}/attempts: HTTP {code}", result["steps"][-1]["error"]
            )

    def test_open_days_skip_completed_and_prefer_in_progress(self):
        # 2026-11-10 개정(#483): 공개된 문제가 쌓이고 마무리한 문제의 새 THEME_DAY는 거부(#506)
        def day(name, mission, status):
            return {"day": name, "missionId": mission, "state": "OPEN", "attemptStatus": status}

        cases = [
            ([day("MON", OTHER_MISSION, "COMPLETED"), day("TUE", TODAY_MISSION, "NOT_STARTED")], TODAY_MISSION),
            ([day("MON", OTHER_MISSION, "NOT_STARTED"), day("TUE", TODAY_MISSION, "IN_PROGRESS")], TODAY_MISSION),
        ]
        for days, expected in cases:
            opener = FakeOpener(theme={**theme(), "days": days})
            self.assertTrue(self.run_smoke(opener)[0]["ok"])
            self.assertEqual(self.started(opener), (expected, {"context": "THEME_DAY"}))
        # 열린 문제를 모두 마무리한 토요일은 되돌아보기 다시 풀기, 평일(되돌아보기 닫힘)은 시작 전 실패
        done = [day("MON", OTHER_MISSION, "COMPLETED")]
        saturday = FakeOpener(theme={**theme(review_open=True, review=[(OTHER_MISSION, True)]), "days": done})
        self.assertTrue(self.run_smoke(saturday)[0]["ok"])
        self.assertEqual(self.started(saturday), (OTHER_MISSION, {"context": "THEME_REVIEW"}))
        weekday = FakeOpener(theme={**theme(), "days": done})
        result, _ = self.run_smoke(weekday)
        self.assertFalse(result["ok"])
        self.assertEqual(result["steps"][-1]["step"], "pick-mission")
        self.assertFalse(any(c[1].endswith("/attempts") for c in weekday.calls))
        self.assertEqual(1, sum(c[1].endswith("/attempts") for c in opener.calls))

    def test_resumed_attempt_with_answer_only_reads_it(self):
        opener = FakeOpener(start_status=200, answers=STORED_ANSWER)
        result, _ = self.run_smoke(opener)
        self.assertTrue(result["ok"])
        self.assertIn("read-answer", [s["step"] for s in result["steps"]])
        self.assertFalse(any(c[1].endswith("/answers") for c in opener.calls))
        self.assertTrue(
            any(c[1].endswith(f"/attempts/{ATTEMPT}") for c in opener.calls)
        )

    def test_resumed_attempt_without_answer_still_submits(self):
        opener = FakeOpener(start_status=200)
        result, _ = self.run_smoke(opener)
        self.assertTrue(result["ok"])
        self.assertIn("submit-answer", [s["step"] for s in result["steps"]])

    def test_read_answer_fails_when_attempt_has_no_answer_id(self):
        opener = FakeOpener(start_status=200, answers=[{"inputType": "NARRATIVE"}])
        result, _ = self.run_smoke(opener)
        self.assertFalse(result["ok"])
        self.assertEqual(result["steps"][-1]["step"], "read-answer")

    def test_answer_follows_the_started_problem_input_type(self):
        choice = {"inputType": "CHOICE", "choiceId": "c-1"}
        opener = FakeOpener(input_type="CHOICE")
        result, _ = self.run_smoke(opener, {**FIXTURE, "answers": [choice]})
        self.assertTrue(result["ok"])
        self.assertEqual(
            next(c[3] for c in opener.calls if c[1].endswith("/answers")), choice
        )
        missing = FakeOpener(input_type="CHOICE")
        result, _ = self.run_smoke(missing)
        self.assertFalse(result["ok"])
        self.assertEqual(result["steps"][-1]["step"], "start-attempt")
        self.assertFalse(any(c[1].endswith("/answers") for c in missing.calls))

    def test_fixture_answers_must_name_input_types(self):
        with self.assertRaises(smoke.CheckFailed):
            self.run_smoke(FakeOpener(), {**FIXTURE, "answers": [{"text": "x"}]})

    def test_missing_rotation_fails(self):
        result, _ = self.run_smoke(FakeOpener(rotate=False))
        self.assertFalse(result["ok"])
        self.assertEqual(result["steps"][-1]["step"], "parent-refresh")

    def test_fixture_must_allow_writes(self):
        with self.assertRaises(smoke.CheckFailed):
            self.run_smoke(FakeOpener(), {**FIXTURE, "allowAnswerSubmission": False})

    def test_base_url_must_be_https_origin(self):
        for value in (
            "http://example.test",
            "https://example.test/api",
            "https://u:p@example.test",
        ):
            with self.subTest(value=value), self.assertRaises(smoke.CheckFailed):
                smoke.base_url(value)


PLAN_RECORD = {
    "environment": "prod",
    "operation": "deploy",
    "sourceCommit": "a" * 40,
    "images": images("learning-service"),
    "planSha256": "f" * 64,
}
ACTIONS_ENV = {
    "GITHUB_ACTOR": "20220348-kim",
    "GITHUB_RUN_ID": "42",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REPOSITORY": "o/r",
}


class RecordTests(unittest.TestCase):
    PLAN = PLAN_RECORD
    ENV = ACTIONS_ENV

    def test_success_needs_deployed_releases_and_smoke(self):
        releases = [
            {
                "release": "learning-service",
                "status": "deployed",
                "revision": 6,
                "previousRevision": 5,
            }
        ]
        ok = record.build(self.PLAN, releases, {"ok": True}, self.ENV, [])
        self.assertEqual(ok["result"], "success")
        self.assertEqual(ok["run"]["url"], "https://github.com/o/r/actions/runs/42")
        self.assertEqual(
            record.build(self.PLAN, releases, {"ok": False}, self.ENV, [])["result"],
            "failure",
        )
        failed = [{**releases[0], "status": "failed"}]
        self.assertEqual(
            record.build(self.PLAN, failed, {"ok": True}, self.ENV, [])["result"],
            "failure",
        )
        self.assertEqual(
            record.build(self.PLAN, None, None, self.ENV, None)["result"], "failure"
        )

    def test_approvals_come_from_github_api(self):
        class Opener:
            def __call__(self, request, timeout=None):
                self.url = request.full_url
                body = [
                    {
                        "user": {"login": "kty2001"},
                        "state": "approved",
                        "environments": [{"name": "prod"}],
                        "comment": "ok",
                    }
                ]
                return FakeResponse(200, body)

        opener = Opener()
        result = record.approvals("o/r", "42", "token", opener=opener)
        self.assertEqual(
            opener.url, "https://api.github.com/repos/o/r/actions/runs/42/approvals"
        )
        self.assertEqual(
            result,
            [
                {
                    "user": "kty2001",
                    "state": "approved",
                    "environments": ["prod"],
                    "comment": True,
                }
            ],
        )
        self.assertIsNone(record.approvals("o/r", "42", None))


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = (ROOT / ".github/workflows/cd-release.yml").read_text(encoding="utf-8")
        cls.text = text
        cls.wf = yaml.safe_load(text)
        cls.jobs = cls.wf["jobs"]

    def test_manual_only_from_main_and_serialized(self):
        self.assertEqual(
            list(self.wf[True]), ["workflow_dispatch"]
        )  # YAML 1.1: on → True
        self.assertIn(
            "github.ref != 'refs/heads/main'", self.jobs["validate"]["steps"][0]["if"]
        )
        self.assertEqual(
            self.wf["concurrency"], {"group": "cd-prod", "cancel-in-progress": False}
        )
        self.assertEqual(self.wf["permissions"], {"contents": "read"})

    def test_approval_gate_runs_on_dedicated_runner_without_cloud_token(self):
        deploy = self.jobs["deploy"]
        self.assertEqual(deploy["environment"], "prod")
        self.assertEqual(deploy["runs-on"], ["self-hosted", "cd-prod"])
        self.assertNotIn("id-token", deploy["permissions"])
        self.assertEqual(self.jobs["publish"]["permissions"]["id-token"], "write")
        self.assertNotIn("environment", self.jobs["publish"])

    def test_disabled_switch_stops_before_publishing_images(self):
        names = [s.get("name", "") for s in self.jobs["validate"]["steps"]]
        self.assertTrue(any("다른 차단 사유가 없어야 함" in n for n in names))
        self.assertEqual(self.jobs["publish"]["needs"], "validate")

    def test_deploy_rechecks_gate_before_apply_and_records_always(self):
        names = [
            step.get("name", step.get("uses")) for step in self.jobs["deploy"]["steps"]
        ]
        gate = names.index("최종 실행 게이트 (실제 이미지·정책 실행 스위치)")
        self.assertLess(gate, names.index("적용 미리보기 (server dry-run)"))
        self.assertLess(
            names.index("적용 미리보기 (server dry-run)"), names.index("적용")
        )
        history = next(
            s for s in self.jobs["deploy"]["steps"] if s.get("name") == "배포 이력 기록"
        )
        self.assertEqual(history["if"], "always()")
        self.assertIn("--require-executable", self.text)
        self.assertNotIn("helm rollback", self.text)

    def test_job_env_uses_only_contexts_github_allows(self):
        # job env에서 runner 컨텍스트를 쓰면 파일 오류로 모든 push에 실패 run이 생긴다
        for name, job in self.jobs.items():
            for value in job.get("env", {}).values():
                self.assertNotIn("runner.", str(value), name)


class CandidateWorkflowTests(unittest.TestCase):
    def test_runs_only_cd_tool_checks_once_per_change(self):
        wf = yaml.safe_load(
            (ROOT / ".github/workflows/cd-candidate.yml").read_text(encoding="utf-8")
        )
        # PR과 브랜치 push가 같은 검사를 두 번 돌리지 않고, 서비스 CI는 서비스별 workflow가 맡는다
        self.assertEqual(set(wf[True]), {"workflow_dispatch", "pull_request"})
        self.assertEqual(list(wf["jobs"]), ["policy"])
        self.assertNotIn("executionEnabled", json.dumps(wf, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
