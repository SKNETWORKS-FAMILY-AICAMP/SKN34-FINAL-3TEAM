"""Validate actual MockMvc JSON (not handcrafted examples) against public schemas."""
from pathlib import Path
import json
import yaml
from jsonschema import Draft202012Validator, FormatChecker
root=Path(__file__).resolve().parents[1]
spec=yaml.safe_load((root/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
for name,schema in {'report':'SupportReport','admin-report':'SupportReport','inquiry':'SupportInquiry','notices':'SupportNoticePage','help':'SupportHelp'}.items():
 data=json.loads((root/f'backend/core-service/build/generated-contracts/support-{name}.json').read_text(encoding='utf-8'))
 Draft202012Validator({**spec['components']['schemas'][schema], 'components': spec['components']},format_checker=FormatChecker()).validate(data)
 print(f'{name}: actual HTTP JSON matches {schema}')
