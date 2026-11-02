"""#42 public operations and shared #42/#50 v1 message contracts. No live provider assumptions."""
import copy
import json
import re
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
EVENTS = ROOT / "contracts/events"


class ReportContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        cls.schemas = {name: json.loads((EVENTS / f"report.{name}.v1.schema.json").read_text(encoding="utf-8"))
                       for name in ("generate", "started", "completed", "failed")}
        cls.sample = {
            "jobId": "11111111-1111-4111-8111-111111111111",
            "studentId": "22222222-2222-4222-8222-222222222222",
            "periodFrom": "2026-10-19", "periodTo": "2026-10-25",
            "trigger": "SCHEDULE", "narrativeEnabled": False,
        }

    def validator(self, name):
        return Draft202012Validator(self.schemas[name], format_checker=FormatChecker())

    def test_public_operations_match_controller_and_all_require_bearer(self):
        controller = ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core/report/controller/ReportController.kt"
        actual = {(method.lower(), path.removeprefix("/api/v1"))
                  for method, path in re.findall(r'@(Get|Post)Mapping\("([^\"]+)"\)', controller.read_text(encoding="utf-8"))}
        documented = {(method, path) for path, methods in self.api["paths"].items()
                      if path.startswith("/reports/") or path == "/children/{childId}/reports"
                      for method in methods if method in {"get", "post"}}
        self.assertEqual(actual, documented)
        self.assertEqual(len(actual), 5)
        self.assertEqual(self.api["security"], [{"BearerAuth": []}])
        for method, path in actual:
            operation = self.api["paths"][path][method]
            self.assertNotIn("security", operation)
            self.assertIn("403", operation["responses"])
            self.assertIn("503", operation["responses"])
        self.assertIn("409", self.api["paths"]["/reports/{reportId}/regenerate"]["post"]["responses"])

    def test_generate_requires_explicit_entitlement_and_disallows_revision_guess_or_pii(self):
        v = self.validator("generate")
        v.validate(self.sample)
        for field in self.sample:
            bad = copy.deepcopy(self.sample); bad.pop(field)
            self.assertTrue(list(v.iter_errors(bad)), field)
        for key, value in {"narrativeEnabled": None, "revision": 2, "nickname": "금지", "studentId": "not-a-uuid", "periodFrom": "not-a-date"}.items():
            bad = copy.deepcopy(self.sample); bad[key] = value
            self.assertTrue(list(v.iter_errors(bad)), key)

    def test_lifecycle_identities_are_identical_and_failure_is_safe_code(self):
        identity = {"jobId": self.sample["jobId"], "studentId": self.sample["studentId"],
                    "reportId": "33333333-3333-4333-8333-333333333333"}
        for name in ("started", "completed", "failed"):
            payload = dict(identity)
            if name == "failed": payload["failureReason"] = "RENDER_FAILED"
            self.validator(name).validate(payload)
            self.assertFalse(self.schemas[name]["additionalProperties"])
            if name == "failed":
                payload["failureReason"] = "학생 원문과 비밀 키"
                self.assertTrue(list(self.validator(name).iter_errors(payload)))
        self.assertEqual(set(self.schemas["started"]["required"]), set(self.schemas["completed"]["required"]))

    def test_existing_topology_routes_all_four_messages_without_new_queue_definitions(self):
        definitions = json.loads((ROOT / "infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json").read_text(encoding="utf-8"))
        bindings = {(b["source"], b["routing_key"], b["destination"]) for b in definitions["bindings"]}
        self.assertIn(("cmd.direct", "report.generate", "report.report.generate"), bindings)
        for name in ("started", "completed", "failed"):
            self.assertIn(("events.topic", f"report.{name}", "core.report.events"), bindings)
        for name, schema in self.schemas.items():
            Draft202012Validator.check_schema(schema)
            self.assertEqual(schema["$id"], f"report.{name}.v1.schema.json")


if __name__ == "__main__":
    unittest.main()
