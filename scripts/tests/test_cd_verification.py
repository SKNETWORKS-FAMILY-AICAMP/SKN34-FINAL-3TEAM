"""HTTP contract checks with a local synthetic server, never a real deployment."""

import json
import sys
import threading
import unittest
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cd_release as cd
import verify_cd_deployment as verify

CHILD, MISSION, REPORT, EXISTING, NEW, ANSWER = [
    f"00000000-0000-4000-8000-{i:012d}" for i in range(1, 7)
]
FIXTURE = {
    "child_id": CHILD,
    "mission_id": MISSION,
    "report_id": REPORT,
    "inflight_attempt_id": EXISTING,
    "payment_order_id": "demo-order",
    "student_pin": "fixture-pin",
    "student_device_cookie": "fixture-device",
    "parent_access_token": "fixture-parent",
    "allowed_payment_states": ["PENDING", "APPROVED"],
    "answer": {"inputType": "NARRATIVE", "text": "Synthetic answer"},
}


class API(BaseHTTPRequestHandler):
    submitted = False
    received: ClassVar[list] = []

    def log_message(self, *args):
        pass

    def response(self, body, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).received.append((self.path, body, dict(self.headers)))
        if self.path == "/api/v1/auth/student/login":
            self.response(
                {
                    "role": "STUDENT",
                    "accessToken": "fixture-student",
                    "child": {"childId": CHILD},
                }
            )
        elif self.path == f"/api/v1/missions/{MISSION}/attempts":
            self.response({"attemptId": NEW}, 201)
        elif self.path == f"/api/v1/attempts/{NEW}/answers":
            type(self).submitted = True
            self.response({"attemptId": NEW, "answerId": ANSWER}, 201)
        else:
            self.response({}, 404)

    def do_GET(self):
        if self.path == f"/api/v1/attempts/{EXISTING}":
            self.response(
                {
                    "attemptId": EXISTING,
                    "status": "IN_PROGRESS",
                    "answers": [{"answerId": "retained", "version": 1}],
                }
            )
        elif self.path == f"/api/v1/attempts/{NEW}":
            self.response(
                {
                    "attemptId": NEW,
                    "answers": [{"answerId": ANSWER}] if self.submitted else [],
                }
            )
        elif self.path == "/api/v1/payments/demo-order":
            self.response(
                {
                    "orderId": "demo-order",
                    "childId": CHILD,
                    "status": "PENDING",
                    "amount": 100,
                }
            )
        elif self.path == f"/api/v1/reports/{REPORT}":
            self.response({"reportId": REPORT, "childId": CHILD, "status": "COMPLETED"})
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/must-not-follow")
            self.end_headers()
        elif self.path == "/html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"login page")
        else:
            self.response({}, 404)


class VerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), API)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_real_http_login_submission_persistence_report_and_impact_contracts(self):
        token = verify.login(self.base, FIXTURE)
        before = verify.impact_snapshot(self.base, FIXTURE, token)
        verify.verify(self.base, FIXTURE, token, "100-1")
        after = verify.impact_snapshot(self.base, FIXTURE, token)
        verify.compare_impact(before, after, FIXTURE)
        self.assertEqual(
            after["payment_status"], "PENDING"
        )  # API property is status, not state.
        serialized = json.dumps(after)
        for secret in (
            CHILD,
            EXISTING,
            "fixture-student",
            "fixture-parent",
            "fixture-device",
            "fixture-pin",
            "Synthetic answer",
        ):
            self.assertNotIn(secret, serialized)
        answer_request = next(r for r in API.received if r[0].endswith("/answers"))
        self.assertIn("Idempotency-Key", answer_request[2])

    def test_login_role_or_identity_mismatch_fails(self):
        with (
            patch.object(
                verify,
                "http_json",
                return_value={
                    "role": "PARENT",
                    "accessToken": "token",
                    "child": {"childId": CHILD},
                },
            ),
            self.assertRaises(ValueError),
        ):
            verify.login(self.base, FIXTURE)

    def test_html_success_and_redirects_are_not_treated_as_success(self):
        for path in ("/html", "/redirect"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                verify.http_json(self.base, path, token="fixture-token")

    def test_exact_multi_source_revision_is_required_even_when_healthy(self):
        app = {
            "status": {
                "sync": {"status": "Synced", "revisions": ["a" * 40, "a" * 40]},
                "health": {"status": "Healthy"},
            }
        }
        self.assertTrue(verify.argo_ready(app, "a" * 40))
        self.assertFalse(verify.argo_ready(app, "b" * 40))
        app["status"]["sync"]["revisions"][1] = "b" * 40
        self.assertFalse(verify.argo_ready(app, "a" * 40))

    def test_inflight_state_loss_or_unreviewed_payment_change_fails(self):
        before = {
            "fixture_hash": "same",
            "attempt_status": "IN_PROGRESS",
            "answers": ["original"],
            "payment_status": "PENDING",
            "payment_amount": 100,
        }
        for field, value in (
            ("answers", []),
            ("attempt_status", "FAILED"),
            ("payment_amount", 200),
            ("payment_status", "CANCELED"),
            ("fixture_hash", "other"),
        ):
            after = dict(before, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify.compare_impact(before, after, FIXTURE)

    def test_rollback_can_use_measured_baseline_when_broken_login_is_unavailable(self):
        before = {
            "fixture_hash": verify.fixture_hash(self.base, FIXTURE),
            "checked_at": cd.stamp(),
        }
        release = {"operation": "rollback", "recovery_baseline": before}
        self.assertEqual(verify.recovery_baseline(release, self.base, FIXTURE), before)
        with self.assertRaises(ValueError):
            verify.recovery_baseline(release, "https://different.example", FIXTURE)
        before["checked_at"] = (cd.now() - timedelta(days=2)).isoformat()
        with self.assertRaises(ValueError):
            verify.recovery_baseline(release, self.base, FIXTURE)
        release["operation"] = "deploy"
        with self.assertRaises(ValueError):
            verify.recovery_baseline(release, self.base, FIXTURE)

    def test_production_rejects_cleartext_and_embedded_credentials(self):
        for address in (
            "http://example.org",
            "https://user:secret@example.org",
            "https://example.org/path?token=secret",
        ):
            with self.subTest(address=address), self.assertRaises(ValueError):
                verify.origin(address, "prod")


if __name__ == "__main__":
    unittest.main()
