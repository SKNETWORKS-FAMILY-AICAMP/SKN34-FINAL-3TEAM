"""#415 load-test account preparation: PIN rules, secrets location and the API order it relies on."""

import importlib.util
import re
import unittest
from pathlib import Path

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

    def test_uses_only_documented_core_paths(self):
        import yaml

        source = (ROOT / "evaluation/load/prepare_accounts.py").read_text(encoding="utf-8")
        spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        calls = re.findall(r'client\.call\("[^"]+", "(GET|POST|PUT)", f?"([^"]+)"', source)
        self.assertGreaterEqual(len(calls), 8)
        for method, path in calls:
            path = re.sub(r"\{kid\['childId'\]\}", "{childId}", path)
            self.assertIn(method.lower(), spec["paths"][path], path)
        k6 = (ROOT / "evaluation/load/core-load.js").read_text(encoding="utf-8")
        self.assertIn("/auth/parent/login", k6)


if __name__ == "__main__":
    unittest.main()
