"""#234 student look values stay identical across OpenAPI, core, migration and web."""

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "backend/core-service/src/main"


def quoted(text):
    return set(re.findall(r"['\"]([a-z]+)['\"]", text))


class StudentLookContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        cls.schemas = spec["components"]["schemas"]
        cls.path = spec["paths"]["/students/me/preferences"]
        cls.themes = set(cls.schemas["StudentLookTheme"]["enum"])
        cls.companions = set(cls.schemas["StudentLookCompanion"]["enum"])

    def test_values_match_core_constants_migration_and_web_domain(self):
        kotlin = (CORE / "kotlin/com/sagomungchi/core/guardianship/domain/StudentLook.kt").read_text(encoding="utf-8")
        migration = (CORE / "resources/db/migration/V23__student_look_preferences.sql").read_text(encoding="utf-8")
        web = (ROOT / "frontend/web/src/domain/studentLook.ts").read_text(encoding="utf-8")
        for name, expected in [("THEMES", self.themes), ("COMPANIONS", self.companions)]:
            self.assertEqual(quoted(re.search(name + r" = setOf\(([^)]*)\)", kotlin)[1]), expected)
        self.assertEqual(quoted(re.search(r"look_theme IN \(([^)]*)\)", migration)[1]), self.themes)
        self.assertEqual(quoted(re.search(r"look_companion IN \(([^)]*)\)", migration)[1]), self.companions)
        self.assertEqual(quoted(re.search(r"type ThemeId = (.*)", web)[1]), self.themes)
        self.assertEqual(quoted(re.search(r"type CompanionId = (.*)", web)[1]), self.companions)
        self.assertIn("{ theme: 'lake', companion: 'mungchi', updatedAt: null }", web)
        self.assertIn('StudentLook("lake", "mungchi", null)', kotlin)

    def test_response_is_closed_and_put_replaces_both_values(self):
        look = self.schemas["StudentLook"]
        self.assertFalse(look["additionalProperties"])
        self.assertEqual(set(look["required"]), {"theme", "companion", "updatedAt"})
        self.assertEqual(set(self.path), {"get", "put"})
        body = self.path["put"]["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(set(body["required"]), {"theme", "companion"})


if __name__ == "__main__":
    unittest.main()
