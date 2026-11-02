"""Validate actual core acceptance/job JSON and the emitted existing report.generate v1 command."""
import json
from pathlib import Path
import jsonschema
import yaml
ROOT=Path(__file__).resolve().parents[1]
spec=yaml.safe_load((ROOT/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
artifacts=ROOT/'backend/core-service/build/admin-retry-contracts'
for filename,name in [('report-retry-accepted.json','ReportRetryAccepted'),('report-retry-job.json','OperationJob')]:
    schema={**spec['components']['schemas'][name],'components':spec['components']}
    jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker()).validate(json.loads((artifacts/filename).read_text(encoding='utf-8')))
    print(f'PASS: actual {filename} matches {name}')
envelope=json.loads((artifacts/'report-retry-generate.json').read_text(encoding='utf-8'))
for schema,data in [('envelope.schema.json',envelope),('report.generate.v1.schema.json',envelope['data'])]:
    jsonschema.Draft202012Validator(json.loads((ROOT/'contracts/events'/schema).read_text(encoding='utf-8')),format_checker=jsonschema.FormatChecker()).validate(data)
    print(f'PASS: actual retry command matches {schema}')
