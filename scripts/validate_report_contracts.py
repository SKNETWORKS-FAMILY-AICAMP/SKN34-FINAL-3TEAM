"""Validate actual core test output against event and OpenAPI schemas; missing files are failures."""
import argparse
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, default=ROOT / "backend/core-service/build/contracts")
    args = parser.parse_args()
    envelope = json.loads((ROOT / "contracts/events/envelope.schema.json").read_text(encoding="utf-8"))
    for name in ("generate", "started", "completed", "failed"):
        message = json.loads((args.runtime_dir / f"report-{name}.json").read_text(encoding="utf-8"))
        Draft202012Validator(envelope, format_checker=FormatChecker()).validate(message)
        data = json.loads((ROOT / f"contracts/events/report.{name}.v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(data, format_checker=FormatChecker()).validate(message["data"])
        if message["subject"] != message["data"]["studentId"] or message["dataschema"] != f"report.{name}.v1":
            raise ValueError("Envelope/data identity mismatch")
        print(f"PASS actual report.{name} envelope/data")
    # P24 #390: the daily command carries periodType; the weekly command keeps the pre-P24 format.
    daily = json.loads((args.runtime_dir / "report-generate-daily.json").read_text(encoding="utf-8"))
    Draft202012Validator(envelope, format_checker=FormatChecker()).validate(daily)
    generate = json.loads((ROOT / "contracts/events/report.generate.v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(generate, format_checker=FormatChecker()).validate(daily["data"])
    weekly = json.loads((args.runtime_dir / "report-generate.json").read_text(encoding="utf-8"))
    if daily["data"].get("periodType") != "DAILY" or "periodType" in weekly["data"]:
        raise ValueError("report.generate periodType: DAILY must be explicit and WEEKLY omitted")
    print("PASS actual daily report.generate envelope/data")
    api = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
    bundle = {"$ref": "#/components/schemas/ReportDetail", "components": api["components"]}
    for name, period_type in (("report-detail.json", "WEEKLY"), ("report-detail-daily.json", "DAILY")):
        detail = json.loads((args.runtime_dir / name).read_text(encoding="utf-8"))
        Draft202012Validator(bundle, format_checker=FormatChecker()).validate(detail)
        if detail["periodType"] != period_type:
            raise ValueError(f"{name}: expected periodType {period_type}")
        if period_type == "WEEKLY" and not (detail.get("explanations") or {}).get("items"):
            raise ValueError(f"{name}: weekly detail must exercise explanations (#508)")
        if period_type == "DAILY" and detail["period"]["from"] != detail["period"]["to"]:
            raise ValueError(f"{name}: a daily report covers one day")
        print(f"PASS actual core HTTP {period_type} report detail vs OpenAPI")


if __name__ == "__main__":
    main()
