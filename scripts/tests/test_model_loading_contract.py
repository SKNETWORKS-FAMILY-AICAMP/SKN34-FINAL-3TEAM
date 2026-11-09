import json
import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[2]

class ModelLoadingContractTest(unittest.TestCase):
    def test_event_schema_and_queue_retry_topology(self):
        schema=json.loads((ROOT/'contracts/events/model.loading.reported.v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        sample={'podId':'scoring-a','instanceId':'00000000-0000-4000-8000-000000000001','sequence':1,'models':[]}
        Draft202012Validator(schema).validate(sample)
        with self.assertRaises(Exception): Draft202012Validator(schema).validate(dict(sample,sequence=0))
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
