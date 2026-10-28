"""Validate actual MockMvc notification JSON against the published OpenAPI schemas."""
import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
artifacts = ROOT / "backend/core-service/build/generated-contracts"
for path, artifact in [("/notifications", "notification-list.json"), ("/notification-settings", "notification-settings.json")]:
    schema = spec["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    schema = {**schema, "components": spec["components"]}
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        json.loads((artifacts / artifact).read_text(encoding="utf-8")))
    print(f"PASS: actual {path} response matches OpenAPI")
