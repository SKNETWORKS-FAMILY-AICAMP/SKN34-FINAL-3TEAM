"""실제 배포 없이 #186의 호환성·승인 누락 차단 검증."""

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


class ReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "environment": "local",
            "operation": "rollback",
            "sourceCommit": "a" * 40,
            "sourceBranch": "develop",
            "services": ["report-service"],
            "currentRelease": "release-2",
            "targetRelease": "release-1",
            "reason": "합성 롤백 검증",
            "databaseAction": "none",
            "images": {
                "report-service": "ghcr.io/example/report-service@sha256:" + "b" * 64
            },
            "previousApproval": {
                "release": "release-1",
                "record": "synthetic/approval-1",
            },
            "compatibility": {
                key: {"status": "compatible", "evidence": "synthetic/test-result"}
                for key in cd.CHECKS
            },
        }
        self.policy = {
            "executionEnabled": False,
            "releaseBranch": "main",
            "approvers": [],
            "environmentProtectionVerified": False,
            "infrastructureReady": False,
        }

    def test_complete_plan_still_cannot_execute(self):
        result = cd.validate(self.plan, self.policy)
        self.assertTrue(result["valid"])
        self.assertFalse(result["executable"])
        self.assertTrue(any("approvers" in item for item in result["blocks"]))

    def test_each_incompatible_or_unknown_check_blocks(self):
        for key in cd.CHECKS:
            for status in ("incompatible", "unknown", None):
                with self.subTest(key=key, status=status):
                    plan = copy.deepcopy(self.plan)
                    plan["compatibility"][key]["status"] = status
                    self.assertIn(
                        f"{key}: 비호환 또는 미확인",
                        cd.validate(plan, self.policy)["blocks"],
                    )

    def test_version_number_alone_is_insufficient(self):
        self.plan["compatibility"] = {"databaseVersion": "20261030_04"}
        self.assertTrue(
            all(
                any(key in b for b in cd.validate(self.plan, self.policy)["blocks"])
                for key in cd.CHECKS
            )
        )

    def test_missing_evidence_blocks(self):
        for key in cd.CHECKS:
            self.plan["compatibility"][key]["evidence"] = " "
        self.assertEqual(
            sum(
                "검증 근거 없음" in x
                for x in cd.validate(self.plan, self.policy)["blocks"]
            ),
            6,
        )

    def test_previous_approval_must_match_target(self):
        self.plan["previousApproval"]["release"] = "another"
        self.assertIn(
            "대상 버전의 이전 승인 기록 없음",
            cd.validate(self.plan, self.policy)["blocks"],
        )

    def test_database_mutations_rejected(self):
        for action in ("downgrade", "restore", None):
            self.plan["databaseAction"] = action
            self.assertFalse(cd.validate(self.plan, self.policy)["valid"])

    def test_mutable_or_wrong_registry_image_rejected(self):
        for image in ("ghcr.io/example/report:latest", "ubuntu@sha256:" + "a" * 64):
            self.plan["images"]["report-service"] = image
            self.assertFalse(cd.validate(self.plan, self.policy)["valid"])

    def test_prod_ecr_digest_accepted(self):
        self.plan["environment"] = "prod"
        self.plan["sourceBranch"] = "main"
        self.plan["images"]["report-service"] = (
            "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/report@sha256:"
            + "c" * 64
        )
        self.assertTrue(cd.validate(self.plan, self.policy)["valid"])

    def test_prod_requires_release_branch(self):
        self.plan["environment"] = "prod"
        self.plan["services"] = ["core-service"]
        self.plan["images"] = {
            "core-service": "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/core@sha256:"
            + "c" * 64
        }
        for branch in ("develop", "feature/x", None, " "):
            with self.subTest(branch=branch):
                self.plan["sourceBranch"] = branch
                self.assertFalse(cd.validate(self.plan, self.policy)["valid"])
        self.plan["sourceBranch"] = "main"
        self.assertTrue(cd.validate(self.plan, self.policy)["valid"])
        self.assertFalse(
            cd.validate(self.plan, {**self.policy, "releaseBranch": None})["valid"]
        )

    def test_repository_policy_is_enabled_but_evidence_still_gates(self):
        # A~C 설정 적용 후 스위치를 켰다(2026-11-04). 근거 없는 계획은 여전히 실행되지 않는다
        policy = json.loads(
            (ROOT / "infrastructure/cd/policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["approvers"], ["20220348-kim", "kty2001"])
        self.assertEqual(policy["releaseBranch"], "main")
        for flag in (
            "executionEnabled",
            "environmentProtectionVerified",
            "infrastructureReady",
        ):
            self.assertIs(policy[flag], True)
        result = cd.validate(self.plan, policy)
        self.assertFalse(
            [b for b in result["blocks"] if "운영 연결" in b or "실행 스위치" in b]
        )
        example = json.loads(
            (ROOT / "infrastructure/cd/plan.example.json").read_text(encoding="utf-8")
        )
        self.assertFalse(cd.validate(example, policy)["executable"])

    def test_plan_approval_flag_is_ignored(self):
        # 승인은 GitHub Environment가 맡는다. 계획의 approved 표시는 결과를 바꾸지 않는다
        blocked = cd.validate({**self.plan, "approved": True}, self.policy)
        self.assertFalse(blocked["executable"])
        ready = {
            "executionEnabled": True,
            "releaseBranch": "main",
            "approvers": ["someone"],
            "environmentProtectionVerified": True,
            "infrastructureReady": True,
        }
        self.assertEqual(
            cd.validate({**self.plan, "approved": False}, ready),
            cd.validate({**self.plan, "approved": True}, ready),
        )
        self.assertTrue(cd.validate(self.plan, ready)["executable"])

    def test_first_install_is_deploy_only(self):
        # #760 빈 클러스터: currentRelease "none"은 되돌릴 버전이 없으므로 rollback에 쓸 수 없다
        self.plan["currentRelease"] = cd.FIRST_INSTALL
        self.assertFalse(cd.validate(self.plan, self.policy)["valid"])
        deploy = {
            **self.plan,
            "operation": "deploy",
            "migrations": {"report-service": self.plan["images"]["report-service"]},
        }
        deploy.pop("previousApproval")
        self.assertTrue(cd.validate(deploy, self.policy)["valid"])

    def test_cli_records_first_install_flag(self):
        for current, expected in ((cd.FIRST_INSTALL, True), ("release-2", False)):
            with self.subTest(current=current), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = {
                    **self.plan,
                    "operation": "deploy",
                    "currentRelease": current,
                    "migrations": {"report-service": self.plan["images"]["report-service"]},
                }
                for name, data in (("plan", plan), ("policy", self.policy)):
                    (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
                run = subprocess.run(
                    [
                        sys.executable, str(Path(cd.__file__)),
                        "--plan", str(root / "plan.json"),
                        "--policy", str(root / "policy.json"),
                        "--output", str(root / "record.json"),
                    ],
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                record = json.loads((root / "record.json").read_text(encoding="utf-8"))
                self.assertIs(record["firstInstall"], expected)
                self.assertEqual(record["currentRelease"], current)

    def test_null_evidence_fails_closed(self):
        self.plan["compatibility"] = None
        self.plan["previousApproval"] = None
        result = cd.validate(self.plan, self.policy)
        self.assertFalse(result["executable"])
        self.assertIn("대상 버전의 이전 승인 기록 없음", result["blocks"])

    def test_broken_korean_text_is_rejected(self):
        # #1004: Windows Git Bash·Python이 CP949로 넘긴 계획. 11/24 #991 사유 일부 그대로
        cases = {
            "reason": "11/24 A À簡µ¿ ù Argo CD ¹èÆ÷ Àü images ÆÄÀÏÀ»",
            "compatibility.schema.evidence": "Ä÷³ »èÁ¦¡¤À̸§ º¯°æ ¾øÀ½",
        }
        for field, text in {**cases, "reason ": "사유��"}.items():
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan)
                if field.startswith("compatibility"):
                    plan["compatibility"]["schema"]["evidence"] = text
                else:
                    plan["reason"] = text
                result = cd.validate(plan, self.policy)
                self.assertFalse(result["valid"])
                self.assertTrue(any("깨진 문자" in e and field.strip() in e for e in result["errors"]))

    def test_normal_korean_text_with_middle_dot_passes(self):
        plan = copy.deepcopy(self.plan)
        plan["reason"] = "core·learning 배포 → 경로 확인(#858), 2×2 확인… “따옴표” café"
        self.assertEqual(cd.broken_text_fields(plan), [])
        self.assertTrue(cd.validate(plan, self.policy)["valid"])

    def test_wrong_field_types_are_invalid_not_exceptions(self):
        for field in ("environment", "operation"):
            for value in ([], {}, None, 123):
                with self.subTest(field=field, value=value):
                    plan = copy.deepcopy(self.plan)
                    plan[field] = value
                    self.assertFalse(cd.validate(plan, self.policy)["valid"])

    def test_cli_malformed_or_nonobject_input_writes_block_record(self):
        for content in ("{broken", "[]", "null"):
            with (
                self.subTest(content=content),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                (root / "plan.json").write_text(content, encoding="utf-8")
                (root / "policy.json").write_text(
                    json.dumps(self.policy), encoding="utf-8"
                )
                run = subprocess.run(
                    [
                        sys.executable,
                        str(Path(cd.__file__)),
                        "--plan",
                        str(root / "plan.json"),
                        "--policy",
                        str(root / "policy.json"),
                        "--output",
                        str(root / "record.json"),
                    ],
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(run.returncode, 2)
                record = json.loads((root / "record.json").read_text(encoding="utf-8"))
                self.assertFalse(record["valid"])
                self.assertFalse(record["executable"])
                self.assertEqual(len(record["policySha256"]), 64)

    def test_cli_writes_audit_without_deploying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (("plan", self.plan), ("policy", self.policy)):
                (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable,
                    str(Path(cd.__file__)),
                    "--plan",
                    str(root / "plan.json"),
                    "--policy",
                    str(root / "policy.json"),
                    "--output",
                    str(root / "record.json"),
                ],
                capture_output=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            record = json.loads((root / "record.json").read_text(encoding="utf-8"))
            self.assertEqual(record["mode"], "plan-validation")
            self.assertFalse(record["executable"])
            self.assertEqual(len(record["planSha256"]), 64)
            self.assertTrue(record["recordedAt"].endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
