"""Keep the small #37 learning producer and its core consumer contract aligned."""
from pathlib import Path
import re
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[2]
class RecordExistsContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=yaml.safe_load((ROOT/'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))
    def test_producer_and_consumer_use_the_same_path(self):
        path='/records/students/{studentId}/exists'
        self.assertEqual(set(self.spec['paths']),{path})
        producer=(ROOT/'backend/learning-service/src/main/kotlin/com/sagomungchi/learning/record/controller/RecordExistsController.kt').read_text(encoding='utf-8')
        consumer=(ROOT/'backend/core-service/src/main/kotlin/com/sagomungchi/core/guardianship/client/ChildRecordsClient.kt').read_text(encoding='utf-8')
        self.assertIn('@GetMapping("/internal'+path+'")',producer)
        self.assertIn('/internal/records/students/{id}/exists',consumer)
        self.assertNotIn('/attempts',consumer)
    def test_only_existence_metadata_is_exposed(self):
        schema=self.spec['components']['schemas']['RecordExists']
        self.assertEqual(set(schema['properties']),{'studentId','hasRecords'})
        self.assertEqual(schema['properties']['hasRecords']['type'],'boolean')
        self.assertFalse(schema['additionalProperties'])
    def test_internal_credentials_and_scope_are_explicit(self):
        op=next(iter(self.spec['paths'].values()))['get']
        self.assertEqual(self.spec['security'],[{'InternalToken':[]}])
        self.assertEqual(self.spec['components']['securitySchemes']['InternalToken']['name'],'X-Internal-Token')
        params={p['name']:p for p in op['parameters']}
        self.assertTrue(params['X-Student-Scope']['required'])
        self.assertEqual(params['X-User-Role']['schema']['enum'],['PARENT','STUDENT','SYSTEM'])
        self.assertTrue({'400','401','403','500'} <= set(op['responses']))
    def test_all_schema_references_resolve(self):
        def visit(node):
            if isinstance(node,dict):
                if '$ref' in node:
                    target=self.spec
                    for part in node['$ref'][2:].split('/'):target=target[part]
                    self.assertIsInstance(target,dict)
                for value in node.values():visit(value)
            elif isinstance(node,list):
                for value in node:visit(value)
        visit(self.spec)
