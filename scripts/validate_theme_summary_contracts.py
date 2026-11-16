"""Check #391 actual learning summary against producer and report consumer contracts."""
import json
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, FormatChecker

root = Path(__file__).resolve().parents[1]
payload = json.loads((root / "backend/learning-service/build/generated-contracts/theme-summary.json").read_text(encoding="utf-8"))
for file, name in [("learning-service.yaml", "WeeklyThemeSummary"), ("report-service.yaml", "ThemeSummary")]:
    spec = yaml.safe_load((root / "contracts/openapi" / file).read_text(encoding="utf-8"))
    Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": spec["components"]}, format_checker=FormatChecker()).validate(payload)
    print(f"PASS: actual learning summary matches {file} {name}")
for retry in payload["reviewRetries"]:
    comparison = retry["comparison"]
    if comparison is not None and set(comparison) != {"state", "elements"}:
        raise ValueError("Comparison must not expose raw answer snapshots")
print("PASS: theme retry comparisons expose only state and element facts")
