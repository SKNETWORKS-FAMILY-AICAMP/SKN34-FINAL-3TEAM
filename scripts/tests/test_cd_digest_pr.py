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


def digest(char):
    return "sha256:" + char * 64


def write_fixture(root, *, registry=REGISTRY, skip=()):
    """#857 계약: image.repository·image.digest, migration은 migration.image.*·migration.revision."""
    folder = Path(root) / POLICY["delivery"]["imagesDir"]
    folder.mkdir(parents=True, exist_ok=True)
    for release, repository in REPOSITORIES.items():
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


def deploy_plan(services=("core-service", "ai-service", "report-service")):
    images = {s: f"{REGISTRY}/sagomungchi/{s}@{digest('a')}" for s in services}
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

    def test_broken_delivery_policy_is_rejected(self):
        for mutate in (
            lambda d: d.pop("imageFiles"),
            lambda d: d["imageFiles"].pop("ai-service"),
            lambda d: d["imageFiles"].update({"ai-service": ["core-service"]}),
            lambda d: d["migrationFiles"].update({"report-service": "core-service"}),
            lambda d: d["migrationFiles"].pop("core-service"),
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
        plan = deploy_plan(tuple(sorted(cd.SERVICES)))
        changes, errors = cd.image_file_updates(plan, POLICY, self.root, allow_repository_change=True)
        self.assertEqual(errors, [])
        self.assertEqual(len(changes), 6)
        for change in changes:
            data = json.loads(change["content"])
            self.assertTrue(data["image"]["repository"].startswith(REGISTRY + "/"))
            self.assertTrue(change["after"]["repository"].startswith(REGISTRY))
            if "migration" in data:
                self.assertTrue(data["migration"]["image"]["repository"].startswith(REGISTRY + "/"))
        body = cd.render_pr_body(plan, changes)
        self.assertIn("저장소 변경(계정 전환)", body)
        self.assertIn("111111111111.dkr.ecr", body)

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
            self.assertIn("prod 이미지 digest 갱신", (root / "body.md").read_text(encoding="utf-8"))

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
