"""Release/rollback regression tests in disposable Git repositories; no deployment."""

import copy
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import cd_release as cd


def images(version=1, environment="local"):
    prefix = (
        "ghcr.io/team/project"
        if environment == "local"
        else "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/project"
    )
    return {
        name: {
            "repository": f"{prefix}/{name}",
            "tag": str(version),
            "digest": "sha256:" + str(version) * 64,
        }
        for name in set(cd.SERVICES) | {"core-migrate", "learning-migrate"}
    }


def review(source, current=None, fingerprint="fingerprint", target=None):
    return {
        "environment": "local",
        "target_source_sha": source,
        "current_deployment": current,
        "config_sha256": fingerprint,
        "rollback_target": target,
        "database_restore": False,
        "checked_at": (cd.now() - timedelta(minutes=1)).isoformat(),
        "expires_at": (cd.now() + timedelta(hours=1)).isoformat(),
        "reviewer": "fixture-reviewer",
        "reason": "Synthetic regression scenario",
        "checks": {
            name: {
                "status": "compatible",
                "summary": "Synthetic reviewed impact",
                "evidence": "test-case",
            }
            for name in cd.CHECKS
        },
    }


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cd186-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in (
            "infrastructure/gitops/charts/app-service",
            "infrastructure/gitops/environments/local",
            "infrastructure/gitops/argocd/local",
        ):
            shutil.copytree(REPO / relative, self.root / relative)
        for app in cd.MIGRATIONS:
            folder = (
                "backend/report-service/migrations/versions"
                if app == "report-api"
                else f"backend/{app}/src/main/resources/db/migration"
            )
            path = (
                self.root
                / folder
                / ("v1.py" if app == "report-api" else "V1__initial.sql")
            )
            path.parent.mkdir(parents=True)
            path.write_text(
                "# fixture\n" if app == "report-api" else "SELECT 1;\n",
                encoding="utf-8",
            )
        self.run_git("init", "-b", "develop")
        self.run_git("config", "user.name", "CD test")
        self.run_git("config", "user.email", "cd-test@example.invalid")
        self.source = self.commit("initial")

    def run_git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()

    def commit(self, message):
        self.run_git("add", ".")
        self.run_git("commit", "-qm", message)
        return self.run_git("rev-parse", "HEAD")

    def make_plan(self, deployment_id="100-1", source=None, target=None):
        source = source or self.source
        current = cd.load_current(self.root, "local")
        request = review(
            source,
            current["id"] if current else None,
            cd.config_hash(self.root, "local"),
            target,
        )
        path = f"infrastructure/gitops/reviews/local/{deployment_id}.json"
        cd.write_json(self.root / path, request)
        self.commit("review")
        result = cd.plan(
            self.root,
            "local",
            "rollback" if target else "deploy",
            source,
            target or "",
            path,
            deployment_id,
        )
        if not target:
            result["images"] = images(1 if deployment_id == "100-1" else 2)
        return result

    def approval(self, release):
        return cd.approval_from_reviews(
            [], "local", "operator", release["id"].split("-")[0]
        )

    def apply(self, release):
        return cd.apply_release(
            self.root,
            self.root,
            release,
            self.approval(release),
            {"fixture_hash": "fixture"},
        )

    def deploy(self, deployment_id="100-1", version=1):
        source_path = self.root / "backend/ai-service/version.txt"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(str(version), encoding="utf-8")
        self.source = self.commit("source")
        release = self.make_plan(deployment_id)
        # The builder has a separate immutable source checkout; simulate that invariant only.
        actual = cd.git
        with patch.object(cd, "git", wraps=cd.git) as git:
            git.side_effect = lambda root, *args: (
                release["source_sha"]
                if root == self.root / "source" and args == ("rev-parse", "HEAD")
                else actual(root, *args)
            )
            source_dir = self.root / "source"
            for app in cd.MIGRATIONS:
                folder = (
                    "backend/report-service/migrations/versions"
                    if app == "report-api"
                    else f"backend/{app}/src/main/resources/db/migration"
                )
                shutil.copytree(
                    self.root / folder, source_dir / folder, dirs_exist_ok=True
                )
            cd.apply_release(
                self.root,
                source_dir,
                release,
                self.approval(release),
                {"fixture_hash": "fixture"},
            )
        gitops = self.commit("GitOps images")
        verification = {
            "deployment_id": deployment_id,
            "gitops_commit": gitops,
            "status": "success",
            "checks": dict.fromkeys(
                (
                    "argo_sync",
                    "login",
                    "learning_submission",
                    "report_query",
                    "inflight_learning",
                    "inflight_payments",
                ),
                True,
            ),
        }
        self.assertTrue(cd.finish(self.root, release, verification, gitops))
        self.commit("verification")
        return release

    def test_first_release_builds_all_and_records_verified_history(self):
        release = self.deploy()
        self.assertEqual(set(release["services"]), set(cd.SERVICES))
        record = cd.load_current(self.root, "local")
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["approval"]["actor"], "operator")
        for app, service in cd.APPS.items():
            value = yaml.safe_load(
                (
                    self.root / f"infrastructure/gitops/environments/local/{app}.yaml"
                ).read_text()
            )
            self.assertEqual(
                value["image"]["digest"], release["images"][service]["digest"]
            )
            if app in cd.MIGRATIONS:
                self.assertTrue(value["migration"]["enabled"])

    def test_rollback_restores_only_app_images_and_never_runs_old_migrations(self):
        first = self.deploy()
        values, history = cd.paths(self.root, "local")
        first_revisions = {
            app: yaml.safe_load((values / f"{app}.yaml").read_text())["migration"][
                "revision"
            ]
            for app in cd.MIGRATIONS
        }
        self.deploy("101-1", version=2)
        before = {
            app: yaml.safe_load((values / f"{app}.yaml").read_text()) for app in cd.APPS
        }
        for app in cd.MIGRATIONS:
            self.assertNotEqual(
                first_revisions[app], before[app]["migration"]["revision"]
            )
        original_history = (history / "100-1.json").read_bytes()
        release = self.make_plan("102-1", source=first["source_sha"], target="100-1")
        self.apply(release)
        for app, service in cd.APPS.items():
            value = yaml.safe_load((values / f"{app}.yaml").read_text())
            self.assertEqual(
                value["image"]["digest"], first["images"][service]["digest"]
            )
            self.assertEqual(value.get("env"), before[app].get("env"))
            if app in cd.MIGRATIONS:
                expected = copy.deepcopy(before[app]["migration"])
                expected["enabled"] = False
                self.assertEqual(value["migration"], expected)
        self.assertEqual((history / "100-1.json").read_bytes(), original_history)
        self.assertEqual(cd.load_current(self.root, "local")["status"], "pending")

    def test_compatibility_unknown_incompatible_or_missing_evidence_blocks(self):
        base = review(self.source)
        for check_name in cd.CHECKS:
            for state in ("unknown", "incompatible", None):
                with self.subTest(check=check_name, state=state):
                    changed = copy.deepcopy(base)
                    changed["checks"][check_name]["status"] = state
                    with self.assertRaises(ValueError):
                        cd.validate_review(
                            changed, "local", self.source, None, "fingerprint"
                        )
            changed = copy.deepcopy(base)
            changed["checks"][check_name]["evidence"] = ""
            with self.assertRaises(ValueError):
                cd.validate_review(changed, "local", self.source, None, "fingerprint")

    def test_review_binds_source_current_config_environment_and_time(self):
        for field, value in {
            "target_source_sha": "0" * 40,
            "current_deployment": "99-1",
            "config_sha256": "different",
            "environment": "prod",
            "database_restore": True,
            "expires_at": (cd.now() - timedelta(hours=1)).isoformat(),
        }.items():
            with self.subTest(field=field):
                changed = review(self.source)
                changed[field] = value
                with self.assertRaises(ValueError):
                    cd.validate_review(
                        changed, "local", self.source, None, "fingerprint"
                    )

    def test_production_requires_actual_approval_by_the_agreed_github_identity(self):
        approved = {
            "state": "approved",
            "user": {"login": cd.APPROVER, "id": cd.APPROVER_ID},
            "environments": [{"name": "prod"}],
        }
        result = cd.approval_from_reviews([approved], "prod", "operator", "100")
        self.assertEqual(result["approved_by"], cd.APPROVER)
        variants = [
            [],
            [dict(approved, state="rejected")],
            [dict(approved, user={"login": "someone", "id": cd.APPROVER_ID})],
            [dict(approved, user={"login": cd.APPROVER, "id": 1})],
            [dict(approved, environments=[{"name": "local"}])],
        ]
        for item in variants:
            with self.subTest(reviews=item), self.assertRaises(ValueError):
                cd.approval_from_reviews(item, "prod", "operator", "100")

    def test_review_revalidation_precedes_any_value_mutation(self):
        release = self.make_plan()
        values, _ = cd.paths(self.root, "local")
        path = values / "core-service.yaml"
        path.write_text(
            path.read_text() + "\n# concurrent configuration change\n", encoding="utf-8"
        )
        before = {p.name: p.read_bytes() for p in values.glob("*.yaml")}
        with self.assertRaises(ValueError):
            self.apply(release)
        self.assertEqual(
            before, {p.name: p.read_bytes() for p in values.glob("*.yaml")}
        )
        self.assertFalse((values / "deployment.json").exists())

    def test_missing_prod_environment_fails_instead_of_inventing_values(self):
        with self.assertRaisesRegex(ValueError, "Missing #171/#185"):
            cd.config_hash(self.root, "prod")

    def test_explicitly_disabled_auto_sync_is_not_treated_as_enabled(self):
        path = self.root / "infrastructure/gitops/argocd/local/apps/applicationset.yaml"
        appset = yaml.safe_load(path.read_text(encoding="utf-8"))
        appset["spec"]["template"]["spec"]["syncPolicy"]["automated"]["enabled"] = False
        path.write_text(yaml.safe_dump(appset), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "automatic sync is not enabled"):
            cd.config_hash(self.root, "local")

    def test_failed_unrelated_or_cross_environment_rollback_target_is_rejected(self):
        self.deploy()
        self.deploy("101-1", 2)
        current = cd.load_current(self.root, "local")
        _, history = cd.paths(self.root, "local")
        for field, value in (("status", "failed"), ("environment", "prod")):
            target = cd.load_record(history, "100-1")
            original = copy.deepcopy(target)
            target[field] = value
            cd.write_json(history / "100-1.json", target)
            with self.assertRaises(ValueError):
                cd.rollback_target(self.root, "local", current, "100-1")
            cd.write_json(history / "100-1.json", original)
        with self.assertRaises(ValueError):
            cd.rollback_target(self.root, "local", current, "999-1")

    def test_service_paths_select_changed_images_and_shared_contracts_select_all(self):
        previous = self.source
        path = self.root / "backend/ai-service/app.py"
        path.parent.mkdir(parents=True)
        path.write_text("# changed AI\n", encoding="utf-8")
        source = self.commit("AI")
        self.assertEqual(
            cd.changed_services(self.root, previous, source), ["ai-service"]
        )
        path = self.root / "contracts/test.json"
        path.parent.mkdir()
        path.write_text("{}", encoding="utf-8")
        source = self.commit("contract")
        self.assertEqual(
            set(cd.changed_services(self.root, previous, source)), set(cd.SERVICES)
        )

    def test_digest_and_environment_registry_validation(self):
        cd.validate_images(images(), "local")
        cd.validate_images(images(environment="prod"), "prod")
        for damaged in (images(), images()):
            damaged["core-service"]["digest"] = "latest"
            with self.assertRaises(ValueError):
                cd.validate_images(damaged, "local")
        with self.assertRaises(ValueError):
            cd.validate_images(images(), "prod")

    def test_generated_history_and_image_updates_do_not_rebuild_every_service(self):
        previous = self.source
        values, history = cd.paths(self.root, "local")
        cd.write_json(history / "100-1.json", {"fixture": True})
        cd.write_json(values / "deployment.json", {"id": "100-1"})
        path = values / "core-service.yaml"
        value = yaml.safe_load(path.read_text())
        value["image"].update(images()["core-service"])
        value["migration"]["revision"] = "generated-revision"
        path.write_text(yaml.safe_dump(value), encoding="utf-8")
        only_metadata = self.commit("generated release metadata")
        self.assertEqual(cd.changed_services(self.root, previous, only_metadata), [])
        value["replicaCount"] = 2
        path.write_text(yaml.safe_dump(value), encoding="utf-8")
        configuration = self.commit("real configuration change")
        self.assertEqual(
            set(cd.changed_services(self.root, only_metadata, configuration)),
            set(cd.SERVICES),
        )

    def test_published_digest_comes_from_build_and_unchanged_images_are_retained(self):
        release = {
            "source_sha": self.source,
            "environment": "local",
            "services": ["ai-service"],
            "images": images(),
        }
        dockerfile = self.root / "backend/ai-service/Dockerfile"
        dockerfile.parent.mkdir(parents=True)
        dockerfile.write_text("FROM scratch\n", encoding="utf-8")
        commands = []

        def build(command, **kwargs):
            commands.append(command)
            cd.write_json(
                Path(command[command.index("--metadata-file") + 1]),
                {"containerimage.digest": "sha256:" + "2" * 64},
            )

        with (
            patch.object(cd, "git", side_effect=[self.source, ""]),
            patch.object(cd.subprocess, "run", side_effect=build),
        ):
            result = cd.publish(release, self.root, "ghcr.io/team/project", self.root)
        self.assertEqual(len(commands), 1)
        self.assertIn("--push", commands[0])
        self.assertEqual(result["images"]["ai-service"]["digest"], "sha256:" + "2" * 64)
        self.assertEqual(
            result["images"]["core-service"]["digest"], "sha256:" + "1" * 64
        )

    def test_result_for_another_run_cannot_finalize_current_deployment(self):
        self.deploy()
        current = cd.load_current(self.root, "local")
        _, history = cd.paths(self.root, "local")
        current["status"] = "pending"
        cd.write_json(history / "100-1.json", current)
        result = {
            "deployment_id": "999-1",
            "gitops_commit": "a" * 40,
            "status": "success",
            "checks": {},
        }
        with self.assertRaises(ValueError):
            cd.finish(self.root, current, result, "a" * 40)

    def test_no_success_from_partial_verification_and_no_late_history_overwrite(self):
        self.deploy()
        current = cd.load_current(self.root, "local")
        _, history = cd.paths(self.root, "local")
        current["status"] = "pending"
        cd.write_json(history / "100-1.json", current)
        result = {
            "deployment_id": "100-1",
            "gitops_commit": "a" * 40,
            "status": "success",
            "checks": {"argo_sync": True},
        }
        self.assertFalse(cd.finish(self.root, current, result, "a" * 40))
        self.assertEqual(cd.load_current(self.root, "local")["status"], "failed")
        with self.assertRaises(ValueError):
            cd.finish(self.root, current, result, "a" * 40)


if __name__ == "__main__":
    unittest.main()
