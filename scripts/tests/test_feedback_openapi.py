"""#39 transport contract; actual learning judgment persistence is outside this check."""
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


class FeedbackOpenApiTests(unittest.TestCase):
    def test_authenticated_sse_contract_and_terminal_events(self):
        spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        operation = spec["paths"]["/answers/{answerId}/feedback"]["post"]
        self.assertEqual(operation["security"], [{"BearerAuth": []}])
        self.assertNotIn("requestBody", operation)
        self.assertEqual([p["name"] for p in operation["parameters"]], ["answerId"])
        self.assertEqual(operation["parameters"][0]["schema"]["format"], "uuid")
        response = operation["responses"]["200"]
        self.assertEqual(response["headers"]["Cache-Control"]["schema"]["const"], "no-store")
        examples = response["content"]["text/event-stream"]["examples"]
        for example in examples.values():
            self.assertTrue(example["value"].endswith("event:done\ndata:{}\n\n"))
        for marker in ("80초", "15초", "90초", "HELD", "RUNNING", "FAILED", "취소하지"):
            self.assertIn(marker, operation["description"])
        self.assertIn("AUTH_UNAVAILABLE", operation["responses"]["503"]["description"])
        self.assertIn("learning-feedback", operation["description"])

    def test_feedback_controller_matches_openapi(self):
        source = (ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/controller/FeedbackController.kt").read_text(encoding="utf-8")
        self.assertIn('@PostMapping("/api/v1/answers/{answerId}/feedback"', source)
        self.assertIn("MediaType.TEXT_EVENT_STREAM_VALUE", source)
        self.assertIn("LEARNING_INVALID_RESPONSE", source)
