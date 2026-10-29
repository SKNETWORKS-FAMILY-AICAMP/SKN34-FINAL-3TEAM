import json
import hashlib
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
        # The CI checkout is shallow. Keep the reviewed base contract fingerprints
        # in the test sources instead of requiring history or network access.
        baseline=json.loads((Path(__file__).parent/'fixtures/admin_operations_base_contracts.json').read_text(encoding='utf-8'))
        self.assertEqual(baseline['sourceCommit'],'85bf1079c34a3e713bcf5eedf0cfdfd7822dc5a4')
        self.assertEqual(baseline['upstreamSourceCommit'],'c44ace8305d7f14b41e48cb24897279aa6cde46a')
        self.assertEqual(len(baseline['paths']),91)
        self.assertEqual(len(baseline['schemas']),114)
        for section,current in [('paths',self.doc['paths']),('schemas',self.doc['components']['schemas'])]:
            for name,expected in baseline[section].items():
                self.assertIn(name,current)
                canonical=json.dumps(current[name],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
                self.assertEqual(expected,hashlib.sha256(canonical).hexdigest(),f'{section}/{name}')
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
