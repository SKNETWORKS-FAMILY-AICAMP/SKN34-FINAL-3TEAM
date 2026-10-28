"""#41 public paths, ownership references and analysis transport contract."""
import re
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]

class ConversationOpenApiTests(unittest.TestCase):
    def setUp(self):
        self.spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))

    def test_public_controller_paths_match_contract(self):
        source = (ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core/conversation/controller/ConversationController.kt").read_text(encoding="utf-8")
        actual = {(method.lower(), path.removeprefix("/api/v1")) for method, path in re.findall(r'@(Get|Post)Mapping\("([^\"]+)"', source)}
        expected = {(method, path) for path, operations in self.spec["paths"].items() for method, op in operations.items() if isinstance(op, dict) and "Conversations" in op.get("tags", [])}
        self.assertEqual(actual, expected)
        self.assertEqual(7, len(expected))

    def test_stream_has_no_json_success_and_retry_path_has_two_owned_ids(self):
        path = "/conversations/{conversationId}/messages/{messageId}/retry"
        op = self.spec["paths"][path]["post"]
        self.assertEqual({"text/event-stream"}, set(op["responses"]["200"]["content"]))
        self.assertEqual({"conversationId", "messageId"}, {p["name"] for p in op["parameters"]})
        evidence = self.spec["components"]["schemas"]["AnalysisEvidence"]
        self.assertIn("evidenceId", evidence["required"])
        self.assertNotIn("quote", evidence["required"])
