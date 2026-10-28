"""ai-service internal routes and their OpenAPI contract stay aligned."""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class AiOpenApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / "contracts/openapi/ai-service.yaml").read_text(encoding="utf-8"))

    def test_documented_operations_match_internal_routers(self):
        actual = set()
        for source in (ROOT / "backend/ai-service/app").rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            prefix = re.search(r'APIRouter\(prefix="([^"]*)"', text)
            for method, path in re.findall(r'@router\.(get|post|put|delete)\("([^"]*)"', text):
                full = (prefix[1] if prefix else "") + path
                if full.startswith("/internal/"):
                    actual.add((method, full.removeprefix("/internal")))
        documented = {(method, path) for path, methods in self.spec["paths"].items() for method in methods}
        self.assertEqual(len(actual), 3)
        self.assertEqual(actual, documented)

    def test_internal_token_and_problem_responses(self):
        self.assertEqual(self.spec["security"], [{"InternalToken": []}])
        self.assertEqual(self.spec["components"]["securitySchemes"]["InternalToken"]["name"], "X-Internal-Token")
        for path in ("/judgments", "/followups"):
            responses = self.spec["paths"][path]["post"]["responses"]
            self.assertTrue({"200", "400", "401", "503"} <= set(responses))
            self.assertNotIn("422", responses)

    def test_held_reason_matches_ai_model(self):
        source = (ROOT / "backend/ai-service/app/judgment/models.py").read_text(encoding="utf-8")
        reasons = re.search(r"HeldReason = Literal\[([^\]]*)\]", source)[1]
        expected = set(re.findall(r'"([A-Z_]+)"', reasons))
        schema = self.spec["components"]["schemas"]["JudgmentResponse"]["properties"]["heldReason"]
        documented = {value for option in schema["anyOf"] for value in option.get("enum", [])}
        self.assertEqual(documented, expected)


if __name__ == "__main__":
    unittest.main()
