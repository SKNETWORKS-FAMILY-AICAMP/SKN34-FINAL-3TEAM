import ast
import json
import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[2]

def _dict_keys(path,class_name,method):
    """클래스 메서드 안에서 문자열 키로만 만든 dict literal 중 가장 큰 것의 키."""
    tree=ast.parse(path.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
    fn=next(n for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==method)
    dicts=[n for n in ast.walk(fn) if isinstance(n,ast.Dict) and n.keys and all(isinstance(k,ast.Constant) and isinstance(k.value,str) for k in n.keys)]
    return set(k.value for k in max(dicts,key=lambda d:len(d.keys)).keys)

class ModelLoadingContractTest(unittest.TestCase):
    def test_event_schema_and_queue_retry_topology(self):
        schema=json.loads((ROOT/'contracts/events/model.loading.reported.v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        sample={'podId':'scoring-a','instanceId':'00000000-0000-4000-8000-000000000001','sequence':1,'models':[]}
        Draft202012Validator(schema).validate(sample)
        with self.assertRaises(Exception): Draft202012Validator(schema).validate(dict(sample,sequence=0))
        # 실제 발행 코드의 필드 이름이 계약과 같아야 한다. 값 검증은 scoring 테스트가 실제 payload로 한다.
        scoring=ROOT/'backend/scoring-service/app'
        reporter=_dict_keys(scoring/'model_loading_reporter.py','ModelLoadingReporter','publish')
        self.assertEqual(reporter,set(schema['required']))
        model=_dict_keys(scoring/'model_registry.py','ModelRegistry','_report')
        item=schema['properties']['models']['items']
        self.assertEqual(model,set(item['required']))
        self.assertEqual(model,set(item['properties']))
        definitions=json.loads((ROOT/'infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json').read_text(encoding='utf-8'))
        names={q['name'] for q in definitions['queues']}
        for suffix in ('','.retry.1','.retry.2','.retry.3','.dlq'):
            self.assertIn('core.model.loading.reported'+suffix,names)
        self.assertTrue(any(b['source']=='events.topic' and b['routing_key']=='model.loading.reported' and b['destination']=='core.model.loading.reported' for b in definitions['bindings']))
    def test_admin_read_contract_is_additive(self):
        api=yaml.safe_load((ROOT/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        self.assertEqual(set(api['paths']['/admin/model-loading']),{'get'})
        schema=api['components']['schemas']['ModelLoadingStatus']
        self.assertEqual(schema['properties']['populationSource']['const'],'RECENT_REPORTS')
