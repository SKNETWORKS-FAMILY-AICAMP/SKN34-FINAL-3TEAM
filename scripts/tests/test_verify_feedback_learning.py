"""#164 verification infrastructure failures; production services are exercised by the runner."""
import importlib.util
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_feedback_learning", ROOT / "scripts/verify_feedback_learning.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class VerificationInfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)
        self.jar = self.output / "fixture.jar"
        self.jar.touch()
        self.args = SimpleNamespace(core_jar=self.jar, learning_jar=self.jar, learning_source=ROOT,
                                    java="java", db_host=None, redis_host=None,
                                    output=self.output / "result.json")
        self.commands = []

    def docker(self, command, **kwargs):
        self.commands.append(command)
        result = ""
        if command[1] == "create":
            result = "redis-id" if "redis:8.2.10-alpine" in command else "db-id"
        elif command[1] == "port":
            result = "127.0.0.1:45678"
        elif command[1] == "inspect":
            result = '[{"Type":"volume","Name":"owned-volume"}]'
        elif "SELECT current_database()" == kwargs.get("input"):
            result = command[command.index("-d") + 1]
        return subprocess.CompletedProcess(command, 0, result, "")

    def run_until_app_start(self, docker=None):
        with patch.object(runner.subprocess, "run", side_effect=docker or self.docker), \
                patch.object(runner, "redis_ready", return_value=True) as ready, \
                patch.object(runner.subprocess, "Popen", side_effect=RuntimeError("app-start")) as app:
            with self.assertRaisesRegex(RuntimeError, "app-start"):
                runner.verify(self.args)
            return app, ready

    def test_learning_uses_actual_core_url_and_isolated_redis_despite_inherited_settings(self):
        with patch.dict(runner.os.environ, {"CORE_URL": "http://localhost:8080", "REDIS_HOST": "shared",
                                          "REDIS_PORT": "6379", "REDIS_PASSWORD": "inherited"}):
            app, ready = self.run_until_app_start()
        env = app.call_args.kwargs["env"]
        self.assertEqual(env["CORE_URL"], env["AUTH_WEB_ORIGIN"])
        self.assertRegex(env["CORE_URL"], r"^http://127\.0\.0\.1:\d+$")
        self.assertEqual((env["REDIS_HOST"], env["REDIS_PORT"], env["REDIS_PASSWORD"]),
                         ("127.0.0.1", "45678", ""))
        ready.assert_called_with("127.0.0.1", 45678)
        self.assertEqual(self.commands[-2:], [["docker", "rm", "-f", "-v", "redis-id"], ["docker", "rm", "-f", "-v", "db-id"]])

    def test_redis_start_failure_removes_both_created_ids(self):
        def fail(command, **kwargs):
            result = self.docker(command, **kwargs)
            if command[1:] == ["start", "redis-id"]:
                return subprocess.CompletedProcess(command, 1, "", "redis startup failed")
            return result
        with patch.object(runner.subprocess, "run", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "redis startup failed"):
                runner.verify(self.args)
        self.assertEqual(self.commands[-2:], [["docker", "rm", "-f", "-v", "redis-id"], ["docker", "rm", "-f", "-v", "db-id"]])

    def test_readiness_failure_still_cleans_up(self):
        with patch.object(runner.subprocess, "run", side_effect=self.docker), \
                patch.object(runner, "redis_ready", side_effect=TimeoutError("redis unreachable")):
            with self.assertRaisesRegex(TimeoutError, "redis unreachable"):
                runner.verify(self.args)
        self.assertEqual(self.commands[-2:], [["docker", "rm", "-f", "-v", "redis-id"], ["docker", "rm", "-f", "-v", "db-id"]])

    def test_cleanup_failure_does_not_skip_other_container_or_hide_original_failure(self):
        def fail(command, **kwargs):
            result = self.docker(command, **kwargs)
            if command[1:] == ["rm", "-f", "-v", "redis-id"]:
                return subprocess.CompletedProcess(command, 1, "", "cleanup denied")
            return result
        with patch.object(runner.subprocess, "run", side_effect=fail), \
                patch.object(runner, "redis_ready", side_effect=TimeoutError("original failure")):
            with self.assertRaisesRegex(TimeoutError, "original failure") as error:
                runner.verify(self.args)
        self.assertIn("cleanup denied", " ".join(error.exception.__notes__))
        self.assertEqual(self.commands[-1], ["docker", "rm", "-f", "-v", "db-id"])

    def test_external_mode_requires_both_dedicated_sidecars_before_any_mutation(self):
        for db, redis in (("issue39-feedback-db-test", None), (None, "issue39-feedback-redis-test"),
                          ("shared", "issue39-feedback-redis-test"), ("issue39-feedback-db-test", "shared")):
            with self.subTest(db=db, redis=redis), patch.object(runner.subprocess, "run") as command:
                self.args.db_host, self.args.redis_host = db, redis
                with self.assertRaises(AssertionError):
                    runner.verify(self.args)
                command.assert_not_called()

    def test_external_mode_never_removes_caller_owned_sidecars(self):
        self.args.db_host, self.args.redis_host = "issue39-feedback-db-test", "issue39-feedback-redis-test"
        psycopg = MagicMock()
        connection = psycopg.connect.return_value.__enter__.return_value
        cursor = connection.execute.return_value
        cursor.description = None
        # Stop at the first SQL operation, after Redis PING, without mutating the sidecars.
        connection.execute.side_effect = RuntimeError("caller SQL failure")
        with patch.dict("sys.modules", {"psycopg": psycopg}), \
                patch.object(runner, "redis_ready", return_value=True) as ready, \
                patch.object(runner.subprocess, "run") as command:
            with self.assertRaisesRegex(RuntimeError, "caller SQL failure"):
                runner.verify(self.args)
            command.assert_not_called()
            ready.assert_called_with("issue39-feedback-redis-test", 6379)

    def test_redis_readiness_requires_pong(self):
        with patch.object(runner.socket, "create_connection") as connect:
            connection = connect.return_value.__enter__.return_value
            reply = connection.makefile.return_value.__enter__.return_value
            for data, expected in ((b"+PONG\r\n", True), (b"-NOAUTH Authentication required\r\n", False), (b"", False)):
                reply.readline.return_value = data
                self.assertEqual(runner.redis_ready("dedicated", 6379), expected)
            connection.sendall.assert_called_with(b"*1\r\n$4\r\nPING\r\n")


if __name__ == "__main__":
    unittest.main()
