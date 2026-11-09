"""계약 산출물이 없는 깨끗한 빌드에서 모든 검증기가 실패해야 한다."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ContractArtifactPresenceTest(unittest.TestCase):
    def test_missing_artifacts_fail_all_validators(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            shutil.copytree(ROOT / "contracts", root / "contracts")
            for name in ("report", "notification", "support", "payment",
                         "admin_report_retry", "analysis", "admin_operations", "reward"):
                with self.subTest(validator=name):
                    script = root / "scripts" / f"validate_{name}_contracts.py"
                    shutil.copyfile(ROOT / "scripts" / script.name, script)
                    args = [sys.executable, "-O", str(script)]
                    if name in ("analysis", "admin_operations"):
                        args.append(str(root / "missing.json"))
                    result = subprocess.run(args, capture_output=True, text=True)
                    self.assertNotEqual(0, result.returncode, result.stdout)
                    self.assertIn("FileNotFoundError", result.stderr)
