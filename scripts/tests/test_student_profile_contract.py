"""Protect the minimal #119 supplier contract and unchanged event boundary."""

from pathlib import Path
import json
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


class StudentProfileContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load(
            (ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8")
        )
        cls.path = cls.spec["paths"]["/internal/students/{studentId}/profile"]
        cls.op = cls.path["get"]

    def test_internal_path_overrides_public_server_and_matches_controller(self):
        self.assertEqual(self.path["servers"], [{"url": "/"}])
        source = (ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core/guardianship/controller/InternalStudentProfileController.kt").read_text(encoding="utf-8")
        self.assertIn('@GetMapping("/internal/students/{studentId}/profile")', source)
        self.assertEqual(self.op["security"], [{"InternalToken": []}])
        self.assertEqual(self.spec["components"]["securitySchemes"]["InternalToken"]["name"], "X-Internal-Token")

    def test_system_scope_and_error_contract(self):
        parameters = {p["name"]: p for p in self.op["parameters"]}
        self.assertTrue(parameters["X-User-Role"]["required"])
        self.assertEqual(parameters["X-User-Role"]["schema"]["enum"], ["SYSTEM"])
        self.assertTrue(parameters["X-Student-Scope"]["required"])
        self.assertEqual(parameters["studentId"]["schema"]["format"], "uuid")
        for status, code in {"400": "VALIDATION_FAILED", "401": "UNAUTHENTICATED", "403": "FORBIDDEN", "404": "NOT_FOUND", "500": "INTERNAL_ERROR"}.items():
            response = self.op["responses"][status]
            self.assertIn(code, response["description"])
            self.assertEqual(response["content"]["application/problem+json"]["schema"]["$ref"], "#/components/schemas/Problem")

    def test_response_has_exactly_two_fields_and_no_store(self):
        schema = self.spec["components"]["schemas"]["InternalStudentProfile"]
        self.assertEqual(set(schema["properties"]), {"studentId", "nickname"})
        self.assertEqual(set(schema["required"]), {"studentId", "nickname"})
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(self.op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"], "#/components/schemas/InternalStudentProfile")
        self.assertEqual(self.op["responses"]["200"]["headers"]["Cache-Control"]["schema"]["const"], "no-store")

    def test_generate_event_stays_free_of_nickname(self):
        schema = json.loads((ROOT / "contracts/events/report.generate.v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(schema["properties"]), {"jobId", "studentId", "periodFrom", "periodTo", "trigger", "narrativeEnabled"})
        self.assertFalse(schema["additionalProperties"])
