"""#894 demo account `children` command: account and GUARDIAN re-consent after a new required document version."""

import importlib.util
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("demo_account_data", ROOT / "infrastructure/aws/demo_account_data.py")
demo_account_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo_account_data)


class FakeApi(demo_account_data.Api):
    def __init__(self, next_action, children):
        self.next_action, self.items, self.calls = next_action, children, []

    def parent(self, creds=None):
        return "test-token", ""

    def call(self, method, path, body=None, token=None, cookie=None, headers=None, raw=False, timeout=180):
        self.calls.append((method, path, body))
        if path == "/consent-documents":
            return 200, {"items": [{"kind": kind, "documentId": kind, "version": "2"}
                                   for kind in ("TERMS", "PRIVACY", "GUARDIAN", "COMMUNITY")]}, ""
        if path == "/me":
            return 200, {"nextAction": self.next_action}, ""
        if (method, path) == ("GET", "/children"):
            return 200, {"items": self.items}, ""
        return 200, {}, ""


def consents(api):
    return [(body.get("childId"), [c["documentId"] for c in body["consents"]])
            for method, path, body in api.calls if path == "/me/consents"]


class DemoChildrenTests(unittest.TestCase):
    def test_rerun_after_new_required_version_gives_account_and_guardian_consent_again(self):
        api = FakeApi("CONSENT_REQUIRED", [{"id": "c1", "nickname": "하나", "grade": 3, "guardianConsentRequired": True},
                                           {"id": "c2", "nickname": "두리", "grade": 5, "guardianConsentRequired": False}])
        demo_account_data.cmd_children(api, Namespace(child=["하나:3", "두리:5"]))
        self.assertEqual(consents(api), [(None, ["TERMS", "PRIVACY"]), ("c1", ["GUARDIAN"])])
        self.assertNotIn(("POST", "/children"), [(m, p) for m, p, _ in api.calls])

    def test_rerun_with_current_consents_changes_nothing(self):
        api = FakeApi("READY", [{"id": "c1", "nickname": "하나", "grade": 3, "guardianConsentRequired": False}])
        demo_account_data.cmd_children(api, Namespace(child=["하나:3", "새별:4"]))
        self.assertEqual(consents(api), [])
        posted = [body for method, path, body in api.calls if (method, path) == ("POST", "/children")]
        self.assertEqual([(b["nickname"], [c["documentId"] for c in b["consents"]]) for b in posted],
                         [("새별", ["GUARDIAN"])])


if __name__ == "__main__":
    unittest.main()
