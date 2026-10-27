"""Public learning proxy contract and implementation boundary checks."""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class LearningOpenApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        cls.source = (ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/controller/LearningController.kt").read_text(encoding="utf-8")

    def test_ten_operations_match_controller_and_keep_feedback_out(self):
        actual = {(method.lower(), path.removeprefix("/api/v1")) for method, path in
                  re.findall(r'@(Get|Post|Put)Mapping\("([^\"]+)"\)', self.source)}
        documented = {(method, path) for path, methods in self.spec["paths"].items()
                      for method, operation in methods.items()
                      if method in {"get", "post", "put"} and "Learning" in operation.get("tags", [])}
        self.assertEqual(len(actual), 10)
        self.assertEqual(actual, documented)
        self.assertFalse(any("feedback" in path for _, path in documented))

    def test_idempotency_and_draft_headers_are_required(self):
        for path, method, header in [("/attempts/{attemptId}/answers", "post", "Idempotency-Key"),
                                     ("/attempts/{attemptId}/draft", "put", "If-Match")]:
            parameters = self.spec["paths"][path][method]["parameters"]
            self.assertEqual(parameters[0]["name"], header)
            self.assertTrue(parameters[0]["required"])
        responses = self.spec["paths"]["/attempts/{attemptId}/answers"]["post"]["responses"]
        self.assertTrue({"201", "409", "422", "503", "504"}.issubset(responses))

    def test_proxy_does_not_access_learning_database_or_add_retry(self):
        directory = ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core/learning"
        sources = "\n".join(file.read_text(encoding="utf-8") for file in directory.rglob("*.kt"))
        for forbidden in ("JdbcTemplate", "DataSource", "@Transactional", "Retry.decorate", "Retry.of", "learning_db"):
            self.assertNotIn(forbidden, sources)
        self.assertIn('factory.create("learning", properties.readTimeout)', sources)
        self.assertIn('headers.set("Idempotency-Key", it)', sources)

    def test_mission_query_only_accepts_pagination_and_derives_profile_in_core(self):
        parameters = self.spec["paths"]["/missions"]["get"]["parameters"]
        self.assertEqual({p["name"] for p in parameters}, {"page", "size"})
        source = (ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/service/LearningProxyService.kt").read_text(encoding="utf-8")
        self.assertIn("students.requireLinked", source)
        self.assertIn('"grade=${student.grade}"', source)
        self.assertIn('"demo=${student.demo}"', source)
