import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]

class MemoryExplanationContractsTest(unittest.TestCase):
    def test_learning_and_core_shapes_match(self):
        core = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        learning = yaml.safe_load((ROOT / "contracts/openapi/learning-service.yaml").read_text(encoding="utf-8"))
        for name in ("MemoryExplanationRequest", "MemoryExplanationResult"):
            self.assertEqual(core["components"]["schemas"][name], learning["components"]["schemas"][name])
        # YAML 1.1 reads a bare `no:` key as boolean False, which hid the citation number checks (#614).
        for doc in (core, learning):
            citation = doc["components"]["schemas"]["MemoryExplanationResult"]["properties"]["citations"]["items"]["properties"]
            self.assertNotIn(False, citation)
            self.assertEqual(citation["no"], {"type": "integer", "minimum": 1, "maximum": 3})
        operation = learning["paths"]["/students/{studentId}/memories/explanations"]["post"]
        self.assertEqual(set(operation["responses"]), {"200", "400", "401", "403", "422", "503"})
        ids = [op["operationId"] for path in learning["paths"].values() for op in path.values() if isinstance(op, dict) and "operationId" in op]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ai_evidence_does_not_include_identifiers(self):
        ai = yaml.safe_load((ROOT / "contracts/openapi/ai-service.yaml").read_text(encoding="utf-8"))
        # The actual request is also checked by the learning HTTP client test.
        self.assertIn("/memory-explanations", ai["paths"])
        source = (ROOT / "backend/learning-service/src/main/kotlin/com/sagomungchi/learning/memory/client/MemoryExplanationAiClient.kt").read_text(encoding="utf-8")
        fields = source.split("data class MemoryEvidence(")[1].split(")")[0]
        for field in ("studentId", "attemptId", "answerId", "nickname"):
            self.assertNotIn(field, fields)
