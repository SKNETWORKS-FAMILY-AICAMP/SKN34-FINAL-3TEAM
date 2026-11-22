"""#415 load-test account preparation: PIN rules, secrets location and the API order it relies on."""

import importlib.util
import json
import re
import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("prepare_accounts", ROOT / "evaluation/load/prepare_accounts.py")
prepare_accounts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_accounts)


class PrepareAccountsTests(unittest.TestCase):
    def test_generated_pins_follow_the_core_pin_rule(self):
        for pin in ("1111", "1234", "654321"):
            self.assertFalse(prepare_accounts.valid_pin(pin), pin)
        self.assertTrue(prepare_accounts.valid_pin("2580"))
        for _ in range(200):
            pin = prepare_accounts.new_pin()
            self.assertRegex(pin, r"^[0-9]{6}$")
            self.assertTrue(prepare_accounts.valid_pin(pin))

    def test_secrets_file_must_stay_outside_the_repository(self):
        self.assertFalse(prepare_accounts.outside_repository(ROOT / "evaluation/load/secrets.json"))
        self.assertFalse(prepare_accounts.outside_repository(ROOT))
        self.assertTrue(prepare_accounts.outside_repository(ROOT.parent / "sagomungchi-load" / "secrets.json"))
        with self.assertRaises(SystemExit):
            prepare_accounts.main(["--secrets", str(ROOT / "secrets.json")])

    def test_prepare_sets_child_pins_without_reauthentication(self):
        class FakeClient:
            def __init__(self, base_url):
                self.calls = []
                self.token = None

            def call(self, step, method, path, body=None, headers=None):
                self.calls.append((method, path, body, headers))
                if path == "/auth/parent/signup":
                    return {"accessToken": "test-token"}
                if path == "/consent-documents":
                    return {"items": [{"kind": kind, "documentId": kind, "version": "1"}
                                      for kind in ("TERMS", "PRIVACY", "GUARDIAN")]}
                if path == "/children":
                    return {"id": str(sum(c[1] == path for c in self.calls))}
                if path == "/student-devices/pairings":
                    return {"pairingCode": "test-pairing"}

            def cookie(self, name):
                return "test-cookie"

        client = FakeClient("http://localhost")
        with patch.object(prepare_accounts, "Client", return_value=client):
            result = prepare_accounts.prepare("http://localhost", "load1", 2, 5, False)
        self.assertEqual([(method, path) for method, path, _, _ in client.calls], [
            ("POST", "/auth/parent/signup"), ("GET", "/consent-documents"),
            ("POST", "/me/consents"), ("POST", "/children"), ("POST", "/children"),
            ("POST", "/student-devices/pairings"), ("POST", "/auth/student/devices"),
            ("PUT", "/children/1/pin"), ("PUT", "/children/2/pin"),
        ])
        for call, kid in zip(client.calls[-2:], result["children"]):
            self.assertEqual(call[2], {"pin": kid["pin"]})
            self.assertIsNone(call[3])
            self.assertTrue(prepare_accounts.valid_pin(kid["pin"]))

    def test_ready_family_gives_guardian_consent_again_after_new_required_version(self):
        """#894: a new GUARDIAN version took effect after the family was prepared; rerunning re-consents first."""
        class FakeClient:
            def __init__(self):
                self.calls = []
                self.token = None

            def call(self, step, method, path, body=None, headers=None):
                self.calls.append((method, path, body))
                if path == "/auth/parent/login":
                    return {"accessToken": "test-token"}
                if path == "/consent-documents":
                    return {"items": [{"kind": kind, "documentId": kind, "version": "2"}
                                      for kind in ("TERMS", "PRIVACY", "GUARDIAN", "COMMUNITY")]}
                if path == "/children":
                    return {"items": [{"id": "c1", "nickname": "하나", "guardianConsentRequired": True},
                                      {"id": "c2", "nickname": "두리", "guardianConsentRequired": False}]}

            def cookie(self, name):
                return "test-cookie"

        family = {"loginId": "dummy1", "name": "더미", "children": [{"nickname": "하나", "grade": 3},
                                                                    {"nickname": "두리", "grade": 5}]}
        entry = {"loginId": "dummy1", "password": "test-password", "deviceCookie": "test-cookie",
                 "children": [{"nickname": "하나", "childId": "c1", "pin": "258014"},
                              {"nickname": "두리", "childId": "c2", "pin": "369025"}]}
        client = FakeClient()
        with TemporaryDirectory() as tmp:
            families = Path(tmp) / "families.json"
            families.write_text(json.dumps({"families": [family]}), encoding="utf-8")
            args = Namespace(families=families, count=None, base_url="http://localhost", wait=False, host=None,
                             origin=None)
            with patch.object(prepare_accounts, "Client", return_value=client):
                self.assertEqual(prepare_accounts.run_families(args, [entry], lambda: None), 0)
        consents = [(body.get("childId"), [c["documentId"] for c in body["consents"]])
                    for method, path, body in client.calls if path == "/me/consents"]
        self.assertEqual(consents, [(None, ["TERMS", "PRIVACY"]), ("c1", ["GUARDIAN"]), ("c1", ["COMMUNITY"]),
                                    ("c2", ["COMMUNITY"])])
        self.assertNotIn("/children", [path for method, path, _ in client.calls if method == "POST"])
        self.assertNotIn("/student-devices/pairings", [path for _, path, _ in client.calls])

    def test_uses_only_documented_core_paths(self):
        import yaml

        source = (ROOT / "evaluation/load/prepare_accounts.py").read_text(encoding="utf-8")
        spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        calls = re.findall(r'client\.call\("[^"]+", "(GET|POST|PUT)", f?"([^"]+)"', source)
        self.assertGreaterEqual(len(calls), 7)
        for method, path in calls:
            path = re.sub(r"\{kid\['childId'\]\}", "{childId}", path)
            self.assertIn(method.lower(), spec["paths"][path], path)
        k6 = (ROOT / "evaluation/load/core-load.js").read_text(encoding="utf-8")
        self.assertIn("/auth/parent/login", k6)


if __name__ == "__main__":
    unittest.main()
