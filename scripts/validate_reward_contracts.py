"""Validate actual MockMvc reward JSON (#389 points, look items, preferences, admin items) against OpenAPI."""
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

root = Path(__file__).resolve().parents[1]
spec = yaml.safe_load((root / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
artifacts = root / "backend/core-service/build/generated-contracts"
for artifact, schema in {
    "reward-points.json": "RewardPoints",
    "reward-look-items.json": "LookCatalog",
    "reward-preferences-equipped.json": "StudentLook",
    "reward-admin-look-item.json": "AdminLookItem",
}.items():
    data = json.loads((artifacts / artifact).read_text(encoding="utf-8"))
    Draft202012Validator({**spec["components"]["schemas"][schema], "components": spec["components"]},
                         format_checker=FormatChecker()).validate(data)
    print(f"PASS: actual {artifact} matches {schema}")
