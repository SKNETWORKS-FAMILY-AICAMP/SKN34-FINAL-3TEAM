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
        # #464: x-implementation-status가 붙은 경로는 계약만 먼저 정한 구현 전 항목(#467 임베딩)
        documented = {
            (method, path)
            for path, methods in self.spec["paths"].items()
            for method, operation in methods.items()
            if not operation.get("x-implementation-status")
        }
        self.assertEqual(len(actual), 8)
        self.assertEqual(actual, documented)

    def test_internal_token_and_problem_responses(self):
        self.assertEqual(self.spec["security"], [{"InternalToken": []}])
        self.assertEqual(self.spec["components"]["securitySchemes"]["InternalToken"]["name"], "X-Internal-Token")
        for path in ("/judgments", "/followups", "/report-narratives", "/mission-drafts"):
            responses = self.spec["paths"][path]["post"]["responses"]
            self.assertTrue({"200", "400", "401", "503"} <= set(responses))
            self.assertNotIn("422", responses)

    def test_held_reason_matches_ai_model(self):
        source = (ROOT / "backend/ai-service/app/judgment/models.py").read_text(encoding="utf-8")
        reasons = re.search(r"HeldReason = Literal\[([^\]]*)\]", source)[1]
        expected = set(re.findall(r'"([A-Z_]+)"', reasons))
        # 판정 응답과 되묻기 요청의 직전 판정 요약은 같은 HeldReason을 쓴다
        for name in ("JudgmentResponse", "JudgmentSummary"):
            schema = self.spec["components"]["schemas"][name]["properties"]["heldReason"]
            documented = {value for option in schema["anyOf"] for value in option.get("enum", [])}
            self.assertEqual(documented, expected, name)

    def test_cross_check_skipped_matches_ai_model(self):
        source = (ROOT / "backend/ai-service/app/judgment/models.py").read_text(encoding="utf-8")
        values = re.search(r"CrossCheckSkipped = Literal\[([^\]]*)\]", source)[1]
        expected = set(re.findall(r'"([A-Z_]+)"', values))
        schema = self.spec["components"]["schemas"]["ModelScores"]["properties"]["skipped"]
        documented = {value for option in schema["anyOf"] for value in option.get("enum", [])}
        self.assertEqual(documented, expected)
        self.assertEqual(expected, {"SCORING_UNAVAILABLE", "SCORING_REJECTED"})

    def test_versions_prompts_match_prompt_scopes(self):
        # 실제 /versions 응답 키는 PROMPT_SCOPES 키와 같다 (#502)
        source = (ROOT / "backend/ai-service/app/prompt_versions/models.py").read_text(encoding="utf-8")
        scopes = re.search(r"PROMPT_SCOPES = \{([^}]*)\}", source)[1]
        expected = set(re.findall(r'"([A-Za-z]+)":', scopes))
        schema = self.spec["paths"]["/versions"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        prompts = schema["properties"]["prompts"]
        self.assertFalse(prompts["additionalProperties"])
        self.assertEqual(set(prompts["required"]), expected)
        self.assertEqual(set(prompts["properties"]), expected)
        self.assertEqual(len(expected), 7)


if __name__ == "__main__":
    unittest.main()
