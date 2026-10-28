"""#40 public dashboard DTOs consume the implemented #27 contract."""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]

class UniqueLoader(yaml.SafeLoader):
    pass

def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result

UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)

def spec(name):
    return yaml.load((ROOT / f'contracts/openapi/{name}-service.yaml').read_text('utf-8'), Loader=UniqueLoader)

class DashboardContractTest(unittest.TestCase):
    def test_public_queries_match_controller_and_provider_is_implemented_once(self):
        core, learning = spec('core'), spec('learning')
        source = (ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/controller/DashboardController.kt').read_text('utf-8')
        paths = {p.removeprefix('/api/v1') for p in re.findall(r'@GetMapping\("([^"]+)"\)', source)}
        documented = {p for p, ops in core['paths'].items() if 'Dashboard' in ops.get('get', {}).get('tags', [])}
        self.assertEqual(paths, documented)
        self.assertEqual(len(paths), 7)
        for suffix in ['home', 'attempts', 'thinking-activities', 'summary', 'thinking-types', 'attempts/{attemptId}']:
            op = learning['paths']['/records/students/{studentId}/' + suffix]['get']
            self.assertNotIn('x-implementation-status', op)
        self.assertFalse(any(n.startswith('Dashboard') for n in learning['components']['schemas']))

    def test_new_record_fields_and_private_draft_boundary(self):
        core, learning = spec('core'), spec('learning')
        for name in ['DashboardPublicAttempt', 'DashboardAttemptDetail', 'DashboardAttempt']:
            shape = core['components']['schemas'][name]
            self.assertTrue({'completedAt', 'hintUsages'}.issubset(shape['required']))
            for field in ['completedAt', 'hintUsages']:
                self.assertEqual(shape['properties'][field], learning['components']['schemas']['RecordAttempt']['properties'][field])
        self.assertIn('createdAt', core['components']['schemas']['DashboardRecordReflection']['required'])
        self.assertNotIn('createdAt', core['components']['schemas']['DashboardReflection']['required'])
        for name in ['DashboardPublicAttempt', 'DashboardAttemptDetail']:
            self.assertNotIn('draft', core['components']['schemas'][name]['properties'])
        self.assertIn('draft', core['components']['schemas']['DashboardAttempt']['properties'])
        self.assertEqual(learning['components']['schemas']['RecordHome']['properties']['resume']['oneOf'][0]['$ref'], '#/components/schemas/RecordAttempt')
        self.assertNotIn('draft', learning['components']['schemas']['RecordAttempt']['properties'])

    def test_internal_identity_and_public_parent_mapping(self):
        learning = spec('learning')
        for name in ['RecordSummary', 'RecordThinkingTypes', 'RecordAttemptPage', 'RecordHome', 'RecordThinkingActivities']:
            shape = learning['components']['schemas'][name]
            self.assertIn('studentId', shape['required'])
            self.assertNotIn('childId', shape['properties'])
        core = spec('core')
        for name in ['DashboardSummary', 'DashboardThinkingTypes', 'DashboardParentAttempts']:
            self.assertIn('childId', core['components']['schemas'][name]['required'])

    def test_frontend_record_adapter_keeps_creation_time(self):
        source = (ROOT / 'frontend/web/src/data/recordDto.ts').read_text('utf-8')
        self.assertIn('createdAt: value.createdAt', source)
        shape = spec('core')['components']['schemas']['DashboardAttemptDetail']['properties']
        self.assertTrue({'attemptId', 'studentId', 'mission', 'answers', 'state', 'period'}.issubset(shape))
