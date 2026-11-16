"""Run the report installer with isolated commands; never install host packages."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "backend/report-service/scripts/install_pdf_runtime.sh"
GIT_SH = Path("C:/Program Files/Git/bin/bash.exe")
SHELL = str(GIT_SH) if os.name == "nt" and GIT_SH.exists() else shutil.which("sh")

STUB = r"""#!/bin/sh
name=${0##*/}
case "$name" in
  id) echo "${TEST_UID:-0}"; exit 0 ;;
  sudo) printf 'sudo:%s\n' "$*" >> "$TEST_DIR/calls"; exec "$@" ;;
  tee) cat > "$TEST_DIR/apt-config"; exit 0 ;;
  sleep) printf 'sleep:%s\n' "$*" >> "$TEST_DIR/calls"; exit 0 ;;
  playwright)
    stage=$1
    [ "$stage" != install ] || stage=browser
    [ "$2" = chromium ] || exit 99
    [ "$PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT" = 45000 ] || exit 98
    ;;
  apt-get) stage=$1; [ "$stage" != install ] || stage=fonts ;;
  *) exit 97 ;;
esac
printf '%s\n' "$stage" >> "$TEST_DIR/calls"
count=0
[ ! -f "$TEST_DIR/$stage.count" ] || count=$(cat "$TEST_DIR/$stage.count")
count=$((count + 1))
echo "$count" > "$TEST_DIR/$stage.count"
if [ "$stage" = "${FAIL_STAGE:-none}" ] && [ "$count" -le "${FAIL_COUNT:-0}" ]; then
  exit 42
fi
"""


class ReportPdfRuntimeTest(unittest.TestCase):
    def invoke(self, stage="none", failures=0, uid=0, arguments=True):
        self.assertIsNotNone(SHELL, "POSIX shell is required for installer tests")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name in ("id", "sudo", "tee", "sleep", "playwright", "apt-get"):
                command = path / name
                command.write_text(STUB, encoding="utf-8", newline="\n")
                command.chmod(0o755)
            env = dict(
                os.environ,
                TEST_DIR=path.as_posix(),
                FAIL_STAGE=stage,
                FAIL_COUNT=str(failures),
                TEST_UID=str(uid),
            )
            env["PATH"] = str(path) + os.pathsep + env["PATH"]
            # Git Bash resets PATH on some Windows setups; explicitly prepend
            # the isolated commands after entering the shell.
            command = 'export PATH="$TEST_DIR:$PATH"; exec sh "$1"'
            if os.name == "nt":
                command = 'export TEST_DIR=$(cygpath -u "$TEST_DIR"); ' + command
            if arguments:
                command += " playwright"
            result = subprocess.run(
                [SHELL, "-c", command, "test", INSTALLER.as_posix()],
                check=False,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            calls = (
                (path / "calls").read_text().splitlines()
                if (path / "calls").exists()
                else []
            )
            config = (
                (path / "apt-config").read_text()
                if (path / "apt-config").exists()
                else ""
            )
            return result, calls, config

    def test_success_and_apt_configuration(self):
        result, calls, config = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["install-deps", "fonts", "browser", "clean"])
        for setting in (
            'Acquire::Retries "3"',
            'Acquire::http::Timeout "30"',
            'Acquire::https::Timeout "30"',
            'APT::Update::Error-Mode "any"',
        ):
            self.assertIn(setting, config)

    def test_dependency_outage_recovers_without_repeating_successful_stages(self):
        result, calls, _ = self.invoke("install-deps", 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls,
            [
                "install-deps",
                "sleep:5",
                "install-deps",
                "sleep:10",
                "install-deps",
                "fonts",
                "browser",
                "clean",
            ],
        )

    def test_persistent_dependency_outage_stops_and_preserves_failure(self):
        result, calls, _ = self.invoke("install-deps", 99)
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertEqual(calls.count("install-deps"), 3)
        self.assertNotIn("fonts", calls)
        self.assertNotIn("clean", calls)

    def test_font_outage_does_not_repeat_dependencies(self):
        result, calls, _ = self.invoke("fonts", 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.count("install-deps"), 1)
        self.assertEqual(calls.count("sleep:5"), 1)

    def test_browser_outage_only_retries_browser(self):
        result, calls, _ = self.invoke("browser", 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.count("install-deps"), 1)
        self.assertEqual(calls.count("fonts"), 1)
        self.assertEqual(calls.count("browser"), 3)

    def test_persistent_font_or_browser_outage_fails(self):
        for stage in ("fonts", "browser"):
            with self.subTest(stage=stage):
                result, calls, _ = self.invoke(stage, 99)
                self.assertEqual(result.returncode, 42, result.stderr)
                self.assertEqual(calls.count(stage), 3)
                self.assertNotIn("clean", calls)

    def test_non_root_runner_uses_sudo(self):
        result, calls, _ = self.invoke(uid=1001)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo:tee /etc/apt/apt.conf.d/80report-pdf-runtime", calls)
        self.assertIn(
            "sudo:apt-get install -y --no-install-recommends fonts-noto-cjk", calls
        )
        self.assertIn("sudo:apt-get clean", calls)

    def test_missing_command_fails_before_system_changes(self):
        result, calls, config = self.invoke(arguments=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])
        self.assertEqual(config, "")


if __name__ == "__main__":
    unittest.main()
