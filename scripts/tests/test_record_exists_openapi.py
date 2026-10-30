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
    def test_documented_operations_match_learning_controllers(self):
        actual=set()
        for source in (ROOT/'backend/learning-service/src/main/kotlin').rglob('*Controller.kt'):
            text=source.read_text(encoding='utf-8')
            prefix=re.search(r'^@RequestMapping\("([^"]*)"\)',text,re.M)
            for method,path in re.findall(r'@(Get|Post|Put|Patch|Delete)Mapping(?:\("([^"]*)"\))?',text):
                actual.add((method.lower(),((prefix[1] if prefix else '')+path).removeprefix('/internal')))
        documented={(method,path) for path,methods in self.spec['paths'].items() for method in methods}
        self.assertEqual(len(actual),35)
        self.assertEqual(actual,documented)
    def test_producer_and_consumer_use_the_same_path(self):
        path='/records/students/{studentId}/exists'
        self.assertIn(path,self.spec['paths'])
        producer=(ROOT/'backend/learning-service/src/main/kotlin/com/sagomungchi/learning/record/controller/RecordExistsController.kt').read_text(encoding='utf-8')
        consumer=(ROOT/'backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/client/LearningRecordClient.kt').read_text(encoding='utf-8')
        self.assertIn('@GetMapping("/internal'+path+'")',producer)
        self.assertIn('/records/students/$studentId/exists',consumer)
        # #40 consumes implemented dashboard queries; exists retains its narrow contract.
    def test_guardianship_calls_learning_service_without_cross_feature_client_access(self):
        source=(ROOT/'backend/core-service/src/main/kotlin/com/sagomungchi/core/guardianship/service/GuardianshipService.kt').read_text(encoding='utf-8')
        self.assertIn('core.learning.service.LearningRecordService',source)
        self.assertNotIn('core.learning.client',source)
        self.assertNotIn('InternalRestClientFactory',source)
    def test_child_mock_draft_defers_to_the_confirmed_contract(self):
        source=(ROOT/'docs/design/api-spec.md').read_text(encoding='utf-8')
        draft=source.split('### 3.7')[1].split('### 3.8')[0]
        self.assertIn('5.3·core OpenAPI',draft)
        self.assertIn('실제 식별자는 `id`',draft)
    def test_only_existence_metadata_is_exposed(self):
        schema=self.spec['components']['schemas']['RecordExists']
        self.assertEqual(set(schema['properties']),{'studentId','hasRecords'})
        self.assertEqual(schema['properties']['hasRecords']['type'],'boolean')
        self.assertFalse(schema['additionalProperties'])
    def test_internal_credentials_and_scope_are_explicit(self):
        op=self.spec['paths']['/records/students/{studentId}/exists']['get']
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
