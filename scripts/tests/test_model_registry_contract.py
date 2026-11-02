"""Contracts for #43 registry, scoped activation and usage queries."""
import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class ModelRegistryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        cls.event = json.loads((ROOT / "contracts/events/model.version.activated.v1.schema.json").read_text(encoding="utf-8"))

    def test_registry_and_usage_operations_match_openapi(self):
        sources = ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core"
        actual = set()
        for source in [sources / "admin/controller/ModelVersionController.kt", sources / "admin/controller/AiUsageController.kt"]:
            for method, path in re.findall(r'@(Get|Post)Mapping\("([^\"]+)"\)', source.read_text(encoding="utf-8")):
                actual.add((method.lower(), path.removeprefix("/api/v1")))
        documented = {(method, path) for path, methods in self.api["paths"].items()
                      if path.startswith("/admin/model-versions") or path in {"/admin/ai-usage", "/internal/model-versions/active"}
                      for method in methods if method in {"get", "post", "put", "patch", "delete"}}
        self.assertEqual(actual, documented)
        self.assertEqual(len(documented), 6)

    def test_internal_snapshot_has_separate_token_and_root_server(self):
        op = self.api["paths"]["/internal/model-versions/active"]["get"]
        self.assertEqual(op["security"], [{"InternalToken": []}])
        self.assertEqual(op["servers"], [{"url": "/"}])
        self.assertEqual(self.api["components"]["securitySchemes"]["InternalToken"]["name"], "X-Internal-Token")
        for path, operations in self.api["paths"].items():
            if path.startswith("/admin/model-versions") or path == "/admin/ai-usage":
                for op in operations.values():
                    self.assertIn("SERVICE_OPS", op["summary"])
                    self.assertIn("403", op["responses"])

    def test_event_schema_is_strict_and_matches_the_snapshot_fields(self):
        snapshot = self.api["components"]["schemas"]["ActiveModelVersion"]
        self.assertEqual(set(self.event["required"]), set(snapshot["required"]) | {"previousVersionId"})
        self.assertFalse(self.event["additionalProperties"])
        self.assertEqual(self.event["properties"]["revision"]["minimum"], 1)
        self.assertNotIn("evaluation", self.event["properties"])
        self.assertNotIn("approvedBy", self.event["properties"])

    def test_activation_requires_explicit_decision_and_rollback_does_not_create_new_approval(self):
        schemas = self.api["components"]["schemas"]
        self.assertEqual(schemas["ActivateModelVersion"]["properties"]["approved"]["const"], True)
        self.assertEqual(set(schemas["ActivateModelVersion"]["required"]), {"approved", "scopes", "reason", "reanalysisPlanned"})
        self.assertNotIn("approvedBy", schemas["ActivateModelVersion"]["properties"])
        self.assertNotIn("approved", schemas["RollbackModelVersion"]["properties"])
        self.assertEqual(schemas["ModelVersion"]["properties"]["status"]["enum"], ["REGISTERED", "ACTIVE", "INACTIVE"])
        self.assertEqual(len(schemas["EvaluationEvidence"]["required"]), 9)

    def test_usage_keeps_null_totals_and_existing_call_type_enum(self):
        schemas = self.api["components"]["schemas"]
        usage = json.loads((ROOT / "contracts/events/llm.usage.recorded.v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schemas["CallType"]["enum"], usage["properties"]["callType"]["enum"])
        self.assertIn("null", schemas["UsageSummary"]["properties"]["costUsd"]["type"])
        self.assertIn("unpricedCalls", schemas["UsageSummary"]["required"])
