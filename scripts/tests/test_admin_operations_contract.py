import json
import subprocess
import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[2]
class AdminOperationsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=yaml.safe_load((ROOT/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
    def test_existing_contracts_preserved(self):
        old=yaml.safe_load(subprocess.check_output(['git','show','85bf107:contracts/openapi/core-service.yaml'],cwd=ROOT).decode())
        for path,methods in old['paths'].items(): self.assertEqual(methods,self.doc['paths'][path],path)
        for name,schema in old['components']['schemas'].items(): self.assertEqual(schema,self.doc['components']['schemas'][name],name)
    def test_admin_paths_and_retry_key(self):
        paths=self.doc['paths']
        for name in ['overview','jobs','queues','audit-logs','missions']: self.assertIn('/admin/'+name,paths)
        retry=paths['/admin/jobs/{jobId}/retry']['post']
        self.assertTrue(any(p['name']=='Idempotency-Key' and p['required'] for p in retry['parameters']))
        self.assertEqual(10,sum(len(v) for k,v in paths.items() if k.startswith('/admin/missions')))
    def test_schema_does_not_invent_updated_at_or_expose_free_text(self):
        schemas=self.doc['components']['schemas']
        self.assertNotIn('updatedAt',schemas['OperationJob']['properties'])
        self.assertNotIn('errorDetail',schemas['OperationExecution']['properties'])
        self.assertNotIn('detail',schemas['OperationAudit']['properties'])
        for name,schema in schemas.items():
            if name.startswith('Operation'): Draft202012Validator.check_schema(schema)
    def test_queue_allowlist(self):
        definition=json.loads((ROOT/'infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json').read_text())
        self.assertEqual(25,len(definition['queues']))
        self.assertEqual({'/'},{q['vhost'] for q in definition['queues']})
