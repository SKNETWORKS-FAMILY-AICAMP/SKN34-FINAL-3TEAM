"""#369 admin account SQL script: core-compatible hash and safe SQL output."""
import argparse
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import admin_account_sql as script  # noqa: E402


class AdminAccountSqlTest(unittest.TestCase):
    def test_hash_matches_core_vector(self):
        # Same vector as core AdminPasswordLoginIntegrationTest (PinHasher.matches).
        self.assertEqual(
            script.password_hash("admin-password-369", bytes(range(16))),
            "pbkdf2-sha256$600000$AAECAwQFBgcICQoLDA0ODw==$RZntp5pQFkl/FFYNwcUI9CU8+AagdjPdN175RnNu7Ek=",
        )

    def test_upsert_escapes_quotes_and_resets_lock(self):
        sql = script.upsert_sql("o'ps", "김'운영", ("CONTENT",), "hash")
        self.assertIn("login_id = 'o''ps'", sql)
        self.assertIn("'김''운영'", sql)
        self.assertIn("failed_count = 0", sql)
        self.assertIn("locked_until = NULL", sql)
        self.assertIn("permission NOT IN ('CONTENT')", sql)
        self.assertTrue(sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;"))

    def test_omitted_permissions_are_kept(self):
        self.assertNotIn("admin_permission", script.upsert_sql("ops", "ops", None, "hash"))

    def test_disable_removes_credential_and_ends_sessions(self):
        sql = script.disable_sql("ops")
        self.assertIn("DELETE FROM admin_credential", sql)
        self.assertIn("UPDATE auth_session SET revoked_at = now()", sql)

    def test_argument_validation(self):
        self.assertEqual(script.permissions("all"), script.PERMISSIONS)
        self.assertEqual(script.permissions("content, service_ops"), ("CONTENT", "SERVICE_OPS"))
        for bad in ("", "OWNER", "CONTENT,OWNER"):
            with self.assertRaises(argparse.ArgumentTypeError):
                script.permissions(bad)
        for bad in ("", "has space", "x" * 255):
            with self.assertRaises(argparse.ArgumentTypeError):
                script.login_id(bad)
        for bad in ("short", "x" * 129):
            with self.assertRaises(ValueError):
                script.check_password(bad)

    def test_password_never_appears_in_output(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"ADMIN_PASSWORD": "plain-secret-369"}), redirect_stdout(out):
            script.main(["--login-id", "ops", "--permissions", "ALL"])
        self.assertNotIn("plain-secret-369", out.getvalue())
        self.assertIn("pbkdf2-sha256$600000$", out.getvalue())


if __name__ == "__main__":
    unittest.main()
