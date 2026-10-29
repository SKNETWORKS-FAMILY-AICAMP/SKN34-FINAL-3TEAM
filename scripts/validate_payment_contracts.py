"""Validate actual payment MockMvc responses; PG and learning are explicit test doubles."""
import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
artifacts = ROOT / "backend/core-service/build/generated-contracts"
for artifact, path, method, status in [
    ("payment-products.json", "/products", "get", "200"),
    ("payment-order.json", "/orders", "post", "201"),
    ("payment-state.json", "/payments/confirm", "post", "200"),
    ("payment-subscriptions.json", "/subscriptions", "get", "200"),
    ("payment-refunded.json", "/payments/{orderId}", "get", "200"),
]:
    schema = spec["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"]
    jsonschema.Draft202012Validator({**schema, "components": spec["components"]}, format_checker=jsonschema.FormatChecker()).validate(
        json.loads((artifacts / artifact).read_text(encoding="utf-8")))
    print(f"PASS: actual {method.upper()} {path} response matches OpenAPI")
