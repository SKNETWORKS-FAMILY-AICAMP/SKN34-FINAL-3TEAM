"""Validate exported actual core analysis SSE results without exporting auth headers."""
import argparse
import json
from pathlib import Path
import jsonschema
import yaml
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("results",type=Path)
args=parser.parse_args()
spec=yaml.safe_load((ROOT/"contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
schema={**spec["components"]["schemas"]["AnalysisFinalResult"],"components":spec["components"]}
validator=jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker())
count=0
for name,case in json.loads(args.results.read_text(encoding="utf-8")).items():
    for event,data in case["events"]:
        if event=="result":
            validator.validate(data)
            count+=1
            print(f"PASS: {name} actual final result")
if count==0:
    raise SystemExit("No final result samples were exported")
print(f"PASS: {count} actual result bodies match the published SSE schema")
