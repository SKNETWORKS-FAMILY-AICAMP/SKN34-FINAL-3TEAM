"""#368 core/scoring contract, least privilege network and read-only S3 policy."""

import json
import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


class PreflightContractTest(unittest.TestCase):
    def test_public_and_internal_payloads_are_identical(self):
        core = yaml.safe_load(
            (ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8")
        )
        scoring = yaml.safe_load(
            (ROOT / "contracts/openapi/scoring-service.yaml").read_text(
                encoding="utf-8"
            )
        )
        for name in (
            "ModelPreflightArtifact",
            "ModelPreflightRequest",
            "ModelPreflightResult",
        ):
            self.assertEqual(
                core["components"]["schemas"][name],
                scoring["components"]["schemas"][name],
            )
        for doc, path in [
            (core, "/admin/models/preflight"),
            (scoring, "/models/preflight"),
        ]:
            self.assertEqual(
                doc["paths"][path]["post"]["requestBody"]["content"][
                    "application/json"
                ]["schema"]["$ref"],
                "#/components/schemas/ModelPreflightRequest",
            )
            Draft202012Validator.check_schema(
                doc["components"]["schemas"]["ModelPreflightResult"]
            )
        self.assertIn(
            "SERVICE_OPS", core["paths"]["/admin/models/preflight"]["post"]["summary"]
        )
        self.assertIn(
            "503", core["paths"]["/admin/models/preflight"]["post"]["responses"]
        )

    def test_both_network_directions_and_service_url_in_each_environment(self):
        for env, ext in [("local", "yaml"), ("prod", "json")]:
            base = ROOT / "infrastructure/gitops/environments" / env
            core = yaml.safe_load(
                (base / f"core-service.{ext}").read_text(encoding="utf-8")
            )
            scoring = yaml.safe_load(
                (base / f"scoring-service.{ext}").read_text(encoding="utf-8")
            )
            self.assertIn(
                {"name": "scoring-service", "port": 8001},
                core["networkPolicy"]["egressToApps"],
            )
            self.assertIn("core-service", scoring["networkPolicy"]["ingressFromApps"])
            self.assertTrue(
                any(
                    e["name"] == "SCORING_URL" and ":8001" in e["value"]
                    for e in core["env"]
                )
            )

    def test_existing_scoring_policy_has_read_but_not_write(self):
        policy = json.loads(
            (
                ROOT
                / "infrastructure/aws/iam/scoring-s3-role.inline.scoring-s3-read.json"
            ).read_text()
        )
        actions = {
            action
            for s in policy["Statement"]
            for action in (
                [s["Action"]] if isinstance(s["Action"], str) else s["Action"]
            )
        }
        self.assertIn("s3:GetObject", actions)
        self.assertNotIn("s3:PutObject", actions)
