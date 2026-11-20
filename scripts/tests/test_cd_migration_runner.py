"""#186 cd-release migration 단계와 #760 빈 클러스터 첫 배포: redeploy-app.ps1의 순서·멱등·실패 처리.

aws·kubectl은 호출을 기록하는 가짜 스크립트로 바꾸고, Job 렌더링은 실제 helm으로 prod values를
그린다. AWS·클러스터에 접속하지 않는다. pwsh·helm이 없으면 건너뛴다.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infrastructure/gitops/environments/prod/redeploy-app.ps1"
DIGEST = "sha256:" + "c" * 64

FAKE_AWS = """
if ($args -contains 'get-caller-identity') { '347161580747'; exit 0 }
if ($args -contains 'describe-cluster') { 'https://fake-eks.example'; exit 0 }
exit 1
"""

# Job 상태는 FAKE_JOB_STATES(쉼표 목록)를 get job 호출마다 하나씩 쓴다(마지막 값 반복)
FAKE_KUBECTL = r"""
$log = $env:FAKE_LOG
Add-Content -LiteralPath $log -Value ($args -join ' ')
if ($args -contains 'config') { '{"clusters":[{"cluster":{"server":"https://fake-eks.example"}}]}'; exit 0 }
if ($args -contains 'get' -and $args -contains 'job') {
  $states = $env:FAKE_JOB_STATES -split ','
  $counter = "$log.count"
  $n = if (Test-Path $counter) { [int](Get-Content $counter) } else { 0 }
  Set-Content $counter ($n + 1)
  $state = $states[[Math]::Min($n, $states.Count - 1)]
  if ($state -eq 'absent') { exit 0 }
  $conditions = switch ($state) {
    'complete' { @(@{ type = 'Complete'; status = 'True' }) }
    'failed' { @(@{ type = 'Failed'; status = 'True' }) }
    default { @() }
  }
  @{ status = @{ conditions = $conditions } } | ConvertTo-Json -Depth 5
  exit 0
}
if ($args -contains 'apply') {
  $file = $args[[array]::IndexOf($args, '-f') + 1]
  Add-Content -LiteralPath $log -Value ('APPLIED ' + ((Get-Content $file | Select-String '^kind: ') -join ','))
  exit 0
}
exit 0
"""


@unittest.skipUnless(shutil.which("pwsh") and shutil.which("helm"), "pwsh·helm 필요")
class MigrationRunnerTests(unittest.TestCase):
    def run_script(self, release, states, *extra):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "aws.ps1").write_text(FAKE_AWS, encoding="utf-8")
            (root / "kubectl.ps1").write_text(FAKE_KUBECTL, encoding="utf-8")
            log = root / "calls.log"
            log.write_text("", encoding="utf-8")
            result = root / "result.json"
            run = subprocess.run(
                [
                    "pwsh", "-NoProfile", "-File", str(SCRIPT),
                    "-Service", release, "-Migration",
                    "-Kubeconfig", str(root / "kubeconfig"),
                    "-Aws", str(root / "aws.ps1"),
                    "-Kubectl", str(root / "kubectl.ps1"),
                    "-ImageDigest", DIGEST, "-Revision", "main-abcdef123456",
                    "-ResultPath", str(result),
                    "-MigrationTimeoutSeconds", "20",
                    *extra,
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
                env={**os.environ, "FAKE_LOG": str(log), "FAKE_JOB_STATES": states},
                check=False,
            )
            calls = log.read_text(encoding="utf-8").splitlines()
            saved = json.loads(result.read_text(encoding="utf-8-sig")) if result.exists() else None
            return run, calls, saved

    def test_preview_server_dry_runs_job_and_policy_without_creating(self):
        run, calls, saved = self.run_script("core-service", "absent")
        self.assertEqual(run.returncode, 0, run.stderr)
        applies = [c for c in calls if c.startswith("--kubeconfig") and " apply " in f" {c} "]
        self.assertEqual(len(applies), 1)
        self.assertIn("--dry-run=server", applies[0])
        self.assertIn("APPLIED kind: NetworkPolicy,kind: Job", calls)
        self.assertEqual(saved["job"], "core-service-migrate-main-abcdef123456")
        self.assertEqual(saved["status"], "preview-absent")
        self.assertTrue(saved["image"].endswith("/sagomungchi/core-migrate@" + DIGEST))

    def test_apply_creates_job_and_waits_until_complete(self):
        run, calls, saved = self.run_script("learning-service", "absent,running,complete", "-Apply")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(any("wait --for=condition=Ready externalsecret" in c for c in calls))
        applies = [c for c in calls if " apply " in f" {c} "]
        self.assertEqual(len(applies), 1)
        self.assertNotIn("--dry-run", applies[0])
        self.assertEqual(saved["status"], "complete")
        self.assertEqual(saved["job"], "learning-service-migrate-main-abcdef123456")

    def test_report_migration_uses_report_api_values_and_app_image(self):
        run, _, saved = self.run_script("report-api", "absent")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(saved["job"], "report-api-migrate-main-abcdef123456")
        self.assertTrue(saved["image"].endswith("/sagomungchi/report-service@" + DIGEST))

    def test_completed_job_is_not_run_again(self):
        run, calls, saved = self.run_script("core-service", "complete", "-Apply")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(any(" apply " in f" {c} " for c in calls))
        self.assertEqual(saved["status"], "already-complete")

    def test_failed_job_stops_without_printing_logs(self):
        for states, extra in (("absent,failed", ("-Apply",)), ("failed", ())):
            with self.subTest(states=states):
                run, calls, saved = self.run_script("core-service", states, *extra)
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(saved["status"], "failed")
                self.assertFalse(any(c.startswith("--kubeconfig") and " logs " in c for c in calls))

    def test_running_job_past_deadline_is_a_timeout(self):
        run, _, saved = self.run_script("core-service", "absent,running", "-Apply")
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(saved["status"], "timeout")

    def test_services_without_migration_values_are_refused(self):
        run, _, saved = self.run_script("ai-service", "absent")
        self.assertNotEqual(run.returncode, 0)
        self.assertIsNone(saved)


# release 상태는 FAKE_RELEASE_STATE 파일("absent" 또는 "<status>:<revision>")에서 읽는다.
# lint·template은 실제 helm(REAL_HELM)에 넘긴다. install·upgrade는 호출만 기록하고 상태를 바꾼다
FAKE_HELM = r"""
$log = $env:FAKE_LOG
$stateFile = $env:FAKE_RELEASE_STATE
if ($args[0] -in 'lint', 'template') { & $env:REAL_HELM @args; exit $LASTEXITCODE }
Add-Content -LiteralPath $log -Value ('HELM ' + ($args -join ' '))
$state = (Get-Content -LiteralPath $stateFile -Raw).Trim()
if ($args[0] -eq 'list') {
  if ($state -eq 'absent') { '[]'; exit 0 }
  $status, $revision = $state -split ':'
  ConvertTo-Json -AsArray @(@{ name = $env:FAKE_RELEASE_NAME; namespace = 'app'; revision = $revision; status = $status })
  exit 0
}
if ($args -contains '--dry-run=server') { exit 0 }
if ($args[0] -in 'install', 'upgrade') {
  if ($env:FAKE_HELM_FAIL) { exit 1 }
  $revision = if ($state -eq 'absent') { 1 } else { [int]($state -split ':')[1] + 1 }
  Set-Content -LiteralPath $stateFile -Value "deployed:$revision"
  exit 0
}
exit 1
"""


@unittest.skipUnless(shutil.which("pwsh") and shutil.which("helm"), "pwsh·helm 필요")
class AppReleaseTests(unittest.TestCase):
    """#760 빈 클러스터: release가 없을 때 -AllowInstall이면 install, 있으면 기존 upgrade 그대로."""

    def run_script(self, release, state, *extra, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "aws.ps1").write_text(FAKE_AWS, encoding="utf-8")
            (root / "kubectl.ps1").write_text(FAKE_KUBECTL, encoding="utf-8")
            (root / "helm.ps1").write_text(FAKE_HELM, encoding="utf-8")
            log = root / "calls.log"
            log.write_text("", encoding="utf-8")
            state_file = root / "release.state"
            state_file.write_text(state, encoding="utf-8")
            result = root / "result.json"
            env = {
                **os.environ,
                "FAKE_LOG": str(log),
                "FAKE_RELEASE_STATE": str(state_file),
                "FAKE_RELEASE_NAME": release,
                "REAL_HELM": shutil.which("helm"),
            }
            if fail:
                env["FAKE_HELM_FAIL"] = "1"
            run = subprocess.run(
                [
                    "pwsh", "-NoProfile", "-File", str(SCRIPT),
                    "-Service", release,
                    "-Kubeconfig", str(root / "kubeconfig"),
                    "-Aws", str(root / "aws.ps1"),
                    "-Kubectl", str(root / "kubectl.ps1"),
                    "-Helm", str(root / "helm.ps1"),
                    "-ImageDigest", DIGEST,
                    "-ResultPath", str(result),
                    *extra,
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
                env=env, check=False,
            )
            calls = log.read_text(encoding="utf-8").splitlines()
            helm = [c[5:] for c in calls if c.startswith("HELM ") and not c.startswith("HELM list ")]
            saved = json.loads(result.read_text(encoding="utf-8-sig")) if result.exists() else None
            return run, helm, saved

    def test_missing_release_is_refused_without_allow_install(self):
        # 기존 재배포 경로는 그대로: release가 없으면 아무것도 적용하지 않고 멈춘다
        for extra in ((), ("-Apply",)):
            with self.subTest(extra=extra):
                run, helm, saved = self.run_script("core-service", "absent", *extra)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("-AllowInstall", run.stderr + run.stdout)
                self.assertEqual(helm, [])
                self.assertIsNone(saved)

    def test_first_install_preview_uses_install_server_dry_run(self):
        run, helm, saved = self.run_script("scoring-service", "absent", "-AllowInstall")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(helm), 1)
        self.assertTrue(helm[0].startswith("install scoring-service "))
        self.assertIn("--dry-run=server", helm[0])
        self.assertEqual(saved["action"], "install")
        self.assertEqual(saved["status"], "preview-install")
        self.assertIsNone(saved["previousRevision"])

    def test_first_install_apply_uses_upgrade_install_and_records_revision(self):
        run, helm, saved = self.run_script("report-worker", "absent", "-AllowInstall", "-Apply")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(helm), 1)
        self.assertTrue(helm[0].startswith("upgrade --install report-worker "))
        self.assertIn("--wait", helm[0])
        self.assertEqual(
            {k: saved[k] for k in ("release", "action", "previousRevision", "revision", "status", "digest")},
            {"release": "report-worker", "action": "install", "previousRevision": None,
             "revision": 1, "status": "deployed", "digest": DIGEST},
        )

    def test_existing_release_keeps_plain_upgrade_even_with_allow_install(self):
        for extra in ((), ("-AllowInstall",)):
            with self.subTest(extra=extra):
                run, helm, saved = self.run_script("core-service", "deployed:7", *extra, "-Apply")
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(len(helm), 1)
                self.assertTrue(helm[0].startswith("upgrade core-service "))
                self.assertNotIn("--install", helm[0])
                self.assertEqual(
                    (saved["action"], saved["previousRevision"], saved["revision"]), ("upgrade", 7, 8)
                )

    def test_existing_release_preview_is_unchanged(self):
        run, helm, saved = self.run_script("learning-service", "deployed:3")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(helm), 1)
        self.assertTrue(helm[0].startswith("upgrade learning-service "))
        self.assertIn("--dry-run=server", helm[0])
        self.assertEqual(saved["status"], "preview-upgrade")

    def test_failed_release_is_not_overwritten(self):
        run, helm, _ = self.run_script("core-service", "failed:1", "-AllowInstall", "-Apply")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("Only an existing deployed app release", run.stderr + run.stdout)
        self.assertEqual(helm, [])

    def test_failed_first_install_is_recorded_as_failed(self):
        run, _, saved = self.run_script("ai-service", "absent", "-AllowInstall", "-Apply", fail=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual((saved["action"], saved["status"]), ("install", "failed"))

    def test_allow_install_is_refused_for_migration(self):
        run, _, saved = self.run_script("core-service", "absent", "-Migration", "-AllowInstall")
        self.assertNotEqual(run.returncode, 0)
        self.assertIsNone(saved)


if __name__ == "__main__":
    unittest.main()
