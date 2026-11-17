"""#186 cd-release migration 단계: redeploy-app.ps1 -Migration의 순서·멱등·실패 처리.

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


if __name__ == "__main__":
    unittest.main()
