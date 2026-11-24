"""#858 digest PR: 계획 → environments/prod/images/<release>.json 갱신과 PR 본문.

#857 images 파일이 develop에 들어오기 전이라 같은 계약(키 이름)의 fixture로 확인한다.
실제 파일이 생기면 RealImagesFileTests가 구조를 함께 본다.
"""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "cd_release", Path(__file__).parents[1] / "cd_release.py"
)
cd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cd)

POLICY = json.loads((ROOT / "infrastructure/cd/policy.json").read_text(encoding="utf-8"))
REGISTRY = "347161580747.dkr.ecr.ap-northeast-2.amazonaws.com"
SHA = "c" * 40
REPOSITORIES = {
    "core-service": "core-service",
    "learning-service": "learning-service",
    "ai-service": "ai-service",
    "scoring-service": "scoring-service",
    "report-api": "report-service",
    "report-worker": "report-service",
}
MIGRATIONS = {"core-service": "core-migrate", "learning-service": "learning-migrate", "report-api": "report-service"}
# 작업 이미지 파일(#985). image만 있고 migration이 없다
JOB_REPOSITORIES = {"tox-retrain": "tox-retrain"}


def digest(char):
    return "sha256:" + char * 64


def write_fixture(root, *, registry=REGISTRY, skip=()):
    """#857 계약: image.repository·image.digest, migration은 migration.image.*·migration.revision."""
    folder = Path(root) / POLICY["delivery"]["imagesDir"]
    folder.mkdir(parents=True, exist_ok=True)
    for release, repository in (REPOSITORIES | JOB_REPOSITORIES).items():
        if release in skip:
            continue
        data = {"image": {"repository": f"{registry}/sagomungchi/{repository}", "digest": digest("0")}}
        if release in MIGRATIONS:
            data["migration"] = {
                "revision": "main-000000000000",
                "image": {"repository": f"{registry}/sagomungchi/{MIGRATIONS[release]}", "digest": digest("0")},
            }
        (folder / f"{release}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return folder


def deploy_plan(services=("core-service", "ai-service", "report-service"), jobs=()):
    images = {s: f"{REGISTRY}/sagomungchi/{s}@{digest('a')}" for s in (*services, *jobs)}
    migrations = {
        s: (images[s] if s == "report-service" else f"{REGISTRY}/sagomungchi/{s.removesuffix('-service')}-migrate@{digest('b')}")
        for s in services
        if s in cd.MIGRATION_REPOSITORIES
    }
    return {
        "environment": "prod",
        "operation": "deploy",
        "sourceCommit": SHA,
        "sourceBranch": "main",
        "services": list(services),
        "jobs": list(jobs),
        "currentRelease": "main-000000000000",
        "targetRelease": "main-" + SHA[:12],
        "reason": "합성 digest PR 확인",
        "databaseAction": "none",
        "images": images,
        "migrations": migrations,
        "compatibility": {k: {"status": "compatible", "evidence": f"synthetic/{k}|ok"} for k in cd.CHECKS},
    }


class DeliveryPolicyTests(unittest.TestCase):
    def test_repository_policy_maps_every_service(self):
        self.assertEqual(cd.validate_delivery(POLICY), [])
        files = [r for names in POLICY["delivery"]["imageFiles"].values() for r in names]
        self.assertEqual(sorted(files), sorted(REPOSITORIES))  # 서비스 5개 → release 파일 6개
        self.assertEqual(set(POLICY["delivery"]["migrationFiles"].values()), set(MIGRATIONS))
        jobs = [r for names in POLICY["delivery"]["jobImageFiles"].values() for r in names]
        self.assertEqual(sorted(jobs), sorted(JOB_REPOSITORIES))

    def test_broken_delivery_policy_is_rejected(self):
        for mutate in (
            lambda d: d.pop("imageFiles"),
            lambda d: d["imageFiles"].pop("ai-service"),
            lambda d: d["imageFiles"].update({"ai-service": ["core-service"]}),
            lambda d: d["migrationFiles"].update({"report-service": "core-service"}),
            lambda d: d["migrationFiles"].pop("core-service"),
            lambda d: d.pop("jobImageFiles"),
            lambda d: d["jobImageFiles"].pop("tox-retrain"),
            lambda d: d["jobImageFiles"].update({"tox-retrain": ["ai-service"]}),  # 앱 파일과 겹침
            lambda d: d["jobImageFiles"].update({"tox-retrain": []}),
        ):
            policy = copy.deepcopy(POLICY)
            mutate(policy["delivery"])
            self.assertTrue(cd.validate_delivery(policy))


class ImageFileUpdateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.folder = write_fixture(self.root)

    def tearDown(self):
        self.dir.cleanup()

    def test_updates_only_planned_releases_and_migrations(self):
        changes, errors = cd.image_file_updates(deploy_plan(), POLICY, self.root)
        self.assertEqual(errors, [])
        self.assertEqual(
            [c["release"] for c in changes], ["core-service", "ai-service", "report-api", "report-worker"]
        )
        core = json.loads(next(c for c in changes if c["release"] == "core-service")["content"])
        self.assertEqual(core["image"]["digest"], digest("a"))
        self.assertEqual(core["migration"]["image"]["digest"], digest("b"))
        self.assertEqual(core["migration"]["revision"], "main-" + SHA[:12])
        api = json.loads(next(c for c in changes if c["release"] == "report-api")["content"])
        # report migration은 같은 앱 이미지(Alembic 포함)
        self.assertEqual(api["migration"]["image"]["digest"], api["image"]["digest"])
        worker = next(c for c in changes if c["release"] == "report-worker")
        self.assertNotIn("migration", worker["after"])
        self.assertTrue(all(c["file"].startswith(POLICY["delivery"]["imagesDir"] + "/") for c in changes))

    def test_other_keys_are_preserved(self):
        path = self.folder / "ai-service.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["image"]["pullPolicy"] = "IfNotPresent"
        data["note"] = "유지"
        path.write_text(json.dumps(data), encoding="utf-8")
        changes, _ = cd.image_file_updates(deploy_plan(), POLICY, self.root)
        ai = json.loads(next(c for c in changes if c["release"] == "ai-service")["content"])
        self.assertEqual(ai["image"]["pullPolicy"], "IfNotPresent")
        self.assertEqual(ai["note"], "유지")

    def test_registry_mismatch_is_an_error_not_a_rewrite(self):
        folder = write_fixture(self.root, registry="111111111111.dkr.ecr.ap-northeast-2.amazonaws.com")
        changes, errors = cd.image_file_updates(deploy_plan(), POLICY, self.root)
        self.assertTrue(any("allowRepositoryChange" in e for e in errors))
        self.assertTrue(folder.exists())

    def test_repository_change_only_when_allowed_for_every_service(self):
        write_fixture(self.root, registry="111111111111.dkr.ecr.ap-northeast-2.amazonaws.com")
        # 일부 서비스만이면 계정이 섞이므로 거부
        _, errors = cd.image_file_updates(deploy_plan(), POLICY, self.root, allow_repository_change=True)
        self.assertTrue(any("전부" in e for e in errors))
        # 서비스 전부여도 작업 이미지(jobs)가 빠지면 tox-retrain.json만 A 주소로 남으므로 거부(#985)
        plan = deploy_plan(tuple(sorted(cd.SERVICES)))
        _, errors = cd.image_file_updates(plan, POLICY, self.root, allow_repository_change=True)
        self.assertTrue(any("jobs" in e for e in errors))
        plan = deploy_plan(tuple(sorted(cd.SERVICES)), tuple(sorted(cd.JOBS)))
        changes, errors = cd.image_file_updates(plan, POLICY, self.root, allow_repository_change=True)
        self.assertEqual(errors, [])
        self.assertEqual(len(changes), 7)
        for change in changes:
            data = json.loads(change["content"])
            self.assertTrue(data["image"]["repository"].startswith(REGISTRY + "/"))
            self.assertTrue(change["after"]["repository"].startswith(REGISTRY))
            if "migration" in data:
                self.assertTrue(data["migration"]["image"]["repository"].startswith(REGISTRY + "/"))
        body = cd.render_pr_body(plan, changes)
        self.assertIn("저장소 변경(계정 전환)", body)
        self.assertIn("111111111111.dkr.ecr", body)

    def test_job_only_plan_updates_only_the_job_file(self):
        # #985: 앱 없이 재학습 이미지만 올리는 계획. migration 키는 만들지 않는다
        plan = deploy_plan((), ("tox-retrain",))
        self.assertTrue(cd.validate(plan, POLICY)["valid"], cd.validate(plan, POLICY))
        changes, errors = cd.image_file_updates(plan, POLICY, self.root)
        self.assertEqual(errors, [])
        self.assertEqual([c["release"] for c in changes], ["tox-retrain"])
        data = json.loads(changes[0]["content"])
        self.assertEqual(data, {"image": {"repository": f"{REGISTRY}/sagomungchi/tox-retrain", "digest": digest("a")}})
        self.assertEqual(changes[0]["file"], POLICY["delivery"]["imagesDir"] + "/tox-retrain.json")
        body = cd.render_pr_body(plan, changes)
        self.assertIn("| tox-retrain | `", body)
        self.assertIn('"jobs": [\n    "tox-retrain"\n  ]', body)  # 계획 기록 JSON
        self.assertIn('"tox-retrain"', body)

    def test_services_and_jobs_together(self):
        plan = deploy_plan(("ai-service",), ("tox-retrain",))
        changes, errors = cd.image_file_updates(plan, POLICY, self.root)
        self.assertEqual(errors, [])
        self.assertEqual([c["release"] for c in changes], ["ai-service", "tox-retrain"])

    def test_job_file_without_image_key_fails(self):
        (self.folder / "tox-retrain.json").write_text('{"image": {"repository": "x"}}', encoding="utf-8")
        self.assertTrue(any("tox-retrain: image.digest" in e for e in cd.check_images_files(POLICY, self.root)))

    def test_missing_file_or_key_fails(self):
        (self.folder / "report-worker.json").unlink()
        _, errors = cd.image_file_updates(deploy_plan(), POLICY, self.root)
        self.assertTrue(any("report-worker" in e for e in errors))
        write_fixture(self.root)
        data = json.loads((self.folder / "learning-service.json").read_text(encoding="utf-8"))
        del data["migration"]["revision"]
        (self.folder / "learning-service.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("migration.revision" in e for e in cd.check_images_files(POLICY, self.root)))

    def test_same_digest_means_nothing_to_do(self):
        plan = deploy_plan(("ai-service",))
        plan["images"]["ai-service"] = f"{REGISTRY}/sagomungchi/ai-service@{digest('0')}"
        changes, errors = cd.image_file_updates(plan, POLICY, self.root)
        self.assertEqual(changes, [])
        self.assertTrue(any("바꿀 digest가 없습니다" in e for e in errors))

    def test_rollback_is_revert_not_a_new_pr(self):
        plan = deploy_plan()
        plan["operation"] = "rollback"
        _, errors = cd.image_file_updates(plan, POLICY, self.root)
        self.assertTrue(any("revert" in e for e in errors))

    def test_pr_body_has_source_digests_plan_and_revert(self):
        plan = deploy_plan()
        changes, _ = cd.image_file_updates(plan, POLICY, self.root)
        body = cd.render_pr_body(plan, changes, run_url="https://example.invalid/run/1", base_sha="d" * 40)
        self.assertIn(SHA, body)
        self.assertIn("d" * 40, body)
        self.assertIn("`000000000000` → `aaaaaaaaaaaa`", body)
        self.assertIn("main-000000000000 → main-" + SHA[:12], body)
        self.assertIn("Revert", body)
        self.assertIn("```json", body)
        self.assertIn("synthetic/schema\\|ok", body)  # 표가 깨지지 않게 | 이스케이프


def git(root, *args):
    run = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
    return run.stdout.decode("utf-8").strip()


def commit_files(root, files, message):
    for path, text in files.items():
        target = Path(root) / path
        if text is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def contract(*paths):
    body = "".join(f"  {p}:\n    get:\n      responses: {{}}\n" for p in paths)
    return f"openapi: 3.1.0\ninfo:\n  title: t\npaths:\n{body}components:\n  schemas: {{}}\n"


class ReleaseHistoryTests(unittest.TestCase):
    """#1013: 이전 migration revision 커밋 → 이번 원본 SHA 사이 migration·API 계약 변경 표시."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        git(self.root, "init", "-q")
        self.old = commit_files(
            self.root,
            {
                cd.MIGRATION_PATHS["core-service"] + "/V1__init.sql": "select 1;\n",
                cd.MIGRATION_PATHS["learning-service"] + "/V1__init.sql": "select 1;\n",
                cd.MIGRATION_PATHS["report-service"] + "/20261103_01_init.py": "x = 1\n",
                cd.CONTRACTS_PATH + "/core-service.yaml": contract("/students/me", "/old"),
                cd.CONTRACTS_PATH + "/report-service.yaml": contract("/reports"),
            },
            "old",
        )

    def tearDown(self):
        self.dir.cleanup()

    def changes(self, revision, services=("core-service", "report-service")):
        releases = {"core-service": "core-service", "learning-service": "learning-service", "report-service": "report-api"}
        return [
            {"service": s, "release": releases[s], "before": {"revision": revision}, "after": {}} for s in services
        ] + [{"service": "ai-service", "release": "ai-service", "before": {"image": digest("0")}, "after": {}}]

    def test_added_migration_and_api_path_mark_revert_risky(self):
        new = commit_files(
            self.root,
            {
                cd.MIGRATION_PATHS["report-service"] + "/20261110_08_report_explanations.py": "x = 2\n",
                cd.CONTRACTS_PATH + "/core-service.yaml": contract("/students/me", "/students/me/weekly-theme"),
                "README.md": "무관한 변경\n",
            },
            "new",
        )
        history = cd.release_history(self.changes("main-" + self.old[:12]), new, self.root)
        core, report = history["services"]
        self.assertEqual((core["service"], core["status"], core["previous"]), ("core-service", "none", self.old))
        self.assertEqual(report["status"], "changed")
        self.assertEqual(report["added"], ["20261110_08_report_explanations.py"])
        self.assertEqual(
            history["api"]["files"],
            [{"file": cd.CONTRACTS_PATH + "/core-service.yaml", "added": ["/students/me/weekly-theme"], "removed": ["/old"]}],
        )
        plan = deploy_plan()
        plan["sourceCommit"] = new
        body = cd.render_pr_body(plan, [], history=history)
        self.assertIn("| core-service | `main-" + self.old[:12] + "` → `main-" + new[:12] + "` | 없음 |", body)
        self.assertIn("**있음** 추가 1개: `20261110_08_report_explanations.py`", body)
        self.assertIn("경로 추가 `/students/me/weekly-theme`", body)
        self.assertIn("경로 삭제 `/old`", body)
        self.assertIn("이 PR을 revert하면 실패할 수 있음", body)
        self.assertIn("fix-forward", body)

    def test_modified_or_deleted_migration_is_also_a_change(self):
        new = commit_files(
            self.root,
            {
                cd.MIGRATION_PATHS["core-service"] + "/V1__init.sql": "select 2;\n",
                cd.MIGRATION_PATHS["report-service"] + "/20261103_01_init.py": None,
            },
            "edit",
        )
        history = cd.release_history(self.changes("main-" + self.old[:12]), new, self.root)
        self.assertEqual([e["other"] for e in history["services"]], [["V1__init.sql(M)"], ["20261103_01_init.py(D)"]])
        self.assertIn("수정·삭제: `V1__init.sql(M)`", cd.render_pr_body(deploy_plan(), [], history=history))

    def test_no_change_means_revert_is_possible(self):
        new = commit_files(self.root, {"README.md": "문서만\n"}, "docs")
        history = cd.release_history(self.changes("main-" + self.old[:12]), new, self.root)
        self.assertEqual([e["status"] for e in history["services"]], ["none", "none"])
        self.assertEqual(history["api"], {"status": "none", "files": [], "partial": False})
        body = cd.render_pr_body(deploy_plan(), [], history=history)
        self.assertIn("migration·API 계약 변경 없음: 문제가 생기면 이 PR revert로 되돌릴 수 있다", body)
        self.assertNotIn("revert하면 실패할 수 있음", body)

    def test_unknown_revision_is_reported_not_failed(self):
        new = commit_files(self.root, {"README.md": "x\n"}, "x")
        # 11/24 main의 report-api처럼 main-<SHA>가 아닌 값, 그리고 저장소에 없는 SHA
        for revision in ("b67d8a462b6b", "main-" + "f" * 12):
            with self.subTest(revision=revision):
                history = cd.release_history(self.changes(revision), new, self.root)
                self.assertEqual([e["status"] for e in history["services"]], ["unknown", "unknown"])
                self.assertEqual(history["api"]["status"], "unknown")
                body = cd.render_pr_body(deploy_plan(), [], history=history)
                self.assertIn("**확인 불가**", body)
                self.assertIn("일부 확인 불가", body)

    def test_one_unknown_service_keeps_other_ranges(self):
        new = commit_files(self.root, {cd.CONTRACTS_PATH + "/report-service.yaml": contract("/reports", "/reports/new")}, "api")
        changes = self.changes("main-" + self.old[:12], ("core-service",)) + [
            {"service": "report-service", "release": "report-api", "before": {"revision": "b67d8a462b6b"}, "after": {}}
        ]
        history = cd.release_history(changes, new, self.root)
        self.assertEqual([e["status"] for e in history["services"]], ["none", "unknown"])
        self.assertEqual(history["api"]["status"], "changed")
        self.assertIn("비교 범위를 모르는 서비스는 빠짐", cd.render_pr_body(deploy_plan(), [], history=history))

    def test_release_without_db_services(self):
        new = commit_files(self.root, {"README.md": "x\n"}, "x")
        history = cd.release_history(self.changes("main-" + self.old[:12], ()), new, self.root)
        self.assertEqual(history["services"], [])
        body = cd.render_pr_body(deploy_plan(), [], history=history)
        self.assertIn("DB를 가진 서비스(core·learning·report)가 없음", body)
        self.assertIn("API 계약(`contracts/openapi`): **확인 불가**", body)

    def test_not_a_git_repository_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            history = cd.release_history(self.changes("main-" + self.old[:12]), self.old, directory)
        self.assertEqual([e["status"] for e in history["services"]], ["unknown", "unknown"])


class CliTests(unittest.TestCase):
    def run_cli(self, root, plan, *extra):
        (root / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        (root / "policy.json").write_text(json.dumps(POLICY), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable, str(Path(cd.__file__)),
                "--plan", str(root / "plan.json"),
                "--policy", str(root / "policy.json"),
                "--output", str(root / "record.json"),
                "--repo-root", str(root),
                *extra,
            ],
            capture_output=True,
            check=False,
        )

    def test_write_images_changes_files_and_writes_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = write_fixture(root)
            untouched = (folder / "scoring-service.json").read_bytes()
            run = self.run_cli(
                root, deploy_plan(), "--require-executable", "--write-images", "--pr-body", str(root / "body.md")
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            record = json.loads((root / "record.json").read_text(encoding="utf-8"))
            self.assertEqual(len(record["imageFileChanges"]), 4)
            self.assertEqual(record["compatibility"]["schema"]["status"], "compatible")
            self.assertEqual((folder / "scoring-service.json").read_bytes(), untouched)
            core = json.loads((folder / "core-service.json").read_text(encoding="utf-8"))
            self.assertEqual(core["image"]["digest"], digest("a"))
            self.assertNotIn(b"\r\n", (folder / "core-service.json").read_bytes())
            body = (root / "body.md").read_text(encoding="utf-8")
            self.assertIn("prod 이미지 digest 갱신", body)
            # 임시 폴더는 git 저장소가 아니라 이전 revision을 찾지 못함 → 실패하지 않고 확인 불가(#1013)
            self.assertIn("revert 판단 자료", body)
            self.assertIn("**확인 불가**", body)

    def test_write_images_body_shows_migration_changes_from_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, "init", "-q")
            write_fixture(root)
            old = commit_files(root, {cd.MIGRATION_PATHS["core-service"] + "/V1__init.sql": "select 1;\n"}, "old")
            folder = root / POLICY["delivery"]["imagesDir"]
            for release in MIGRATIONS:
                data = json.loads((folder / f"{release}.json").read_text(encoding="utf-8"))
                data["migration"]["revision"] = "main-" + old[:12]
                (folder / f"{release}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            new = commit_files(root, {cd.MIGRATION_PATHS["core-service"] + "/V2__add.sql": "select 2;\n"}, "new")
            plan = deploy_plan()
            plan["sourceCommit"] = new
            plan["targetRelease"] = "main-" + new[:12]
            run = self.run_cli(root, plan, "--require-executable", "--write-images", "--pr-body", str(root / "body.md"))
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            body = (root / "body.md").read_text(encoding="utf-8")
            self.assertIn("**있음** 추가 1개: `V2__add.sql`", body)
            self.assertIn("| report-service | `main-" + old[:12], body)
            self.assertIn("이 PR을 revert하면 실패할 수 있음", body)

    def test_any_error_writes_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = write_fixture(root)
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            plan = deploy_plan()
            # 하나만 저장소가 달라도 나머지 파일도 쓰지 않는다
            data = json.loads((folder / "report-worker.json").read_text(encoding="utf-8"))
            data["image"]["repository"] = "111111111111.dkr.ecr.ap-northeast-2.amazonaws.com/sagomungchi/report-service"
            (folder / "report-worker.json").write_text(json.dumps(data), encoding="utf-8")
            before["report-worker.json"] = (folder / "report-worker.json").read_bytes()
            run = self.run_cli(root, plan, "--require-executable", "--write-images", "--pr-body", str(root / "body.md"))
            self.assertEqual(run.returncode, 2)
            self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)
            self.assertFalse((root / "body.md").exists())

    def test_blocked_plan_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = write_fixture(root)
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            plan = deploy_plan()
            plan["compatibility"]["schema"]["status"] = "unknown"
            run = self.run_cli(root, plan, "--require-executable", "--write-images")
            self.assertEqual(run.returncode, 3)
            self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)

    def test_check_images_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = deploy_plan()
            plan.pop("images")
            plan.pop("migrations")
            run = self.run_cli(root, plan, "--pending-images", "--check-images")
            self.assertEqual(run.returncode, 2)  # images 파일이 아직 없음(#857 전)
            record = json.loads((root / "record.json").read_text(encoding="utf-8"))
            self.assertTrue(any("images 파일이 없거나" in e for e in record["errors"]))
            write_fixture(root)
            run = self.run_cli(root, plan, "--pending-images", "--check-images")
            self.assertEqual(run.returncode, 0, run.stdout)
            plan["operation"] = "rollback"
            run = self.run_cli(root, plan, "--pending-images", "--check-images")
            self.assertEqual(run.returncode, 2)

    def test_write_images_needs_the_final_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            run = self.run_cli(Path(directory), deploy_plan(), "--write-images")
            self.assertEqual(run.returncode, 2)  # argparse 오류


@unittest.skipUnless(
    (ROOT / POLICY["delivery"]["imagesDir"]).is_dir(), "#857 images 파일이 아직 없음"
)
class RealImagesFileTests(unittest.TestCase):
    def test_repository_images_files_follow_contract(self):
        self.assertEqual(cd.check_images_files(POLICY, ROOT), [])


if __name__ == "__main__":
    unittest.main()
