"""Validate exported actual admin HTTP responses against the published core OpenAPI.

Usage: python scripts/validate_admin_operations_contracts.py responses.json
The JSON object maps Operation* schema names to actual response bodies; never export tokens.
"""
import argparse
import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("responses", type=Path)
args = parser.parse_args()
spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
responses = json.loads(args.responses.read_text(encoding="utf-8"))
expected = {"OperationOverview", "OperationJobPage", "OperationJob", "OperationQueues", "OperationAuditPage"}
if set(responses) != expected:
    raise SystemExit("Export exactly the five admin response schemas: " + ", ".join(sorted(expected)))
for name in sorted(expected):
    schema = {**spec["components"]["schemas"][name], "components": spec["components"]}
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(responses[name])
    print(f"PASS: actual {name} response matches OpenAPI")
