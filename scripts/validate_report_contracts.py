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
    api = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
    bundle = {"$ref": "#/components/schemas/ReportDetail", "components": api["components"]}
    detail = json.loads((args.runtime_dir / "report-detail.json").read_text(encoding="utf-8"))
    Draft202012Validator(bundle, format_checker=FormatChecker()).validate(detail)
    print("PASS actual core HTTP report detail vs OpenAPI")


if __name__ == "__main__":
    main()
