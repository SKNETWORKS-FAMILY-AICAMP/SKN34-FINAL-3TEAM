"""#40 consumer contracts distinguish planned #27 producers from implemented endpoints."""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


class DashboardContractTest(unittest.TestCase):
    def test_seven_public_queries_and_six_planned_supplier_paths(self):
        core = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text('utf-8'))
        learning = yaml.safe_load((ROOT / 'contracts/openapi/learning-service.yaml').read_text('utf-8'))
        source = (ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/controller/DashboardController.kt').read_text('utf-8')
        paths = {p.removeprefix('/api/v1') for p in re.findall(r'@GetMapping\("([^"]+)"\)', source)}
        documented = {p for p, ops in core['paths'].items() if 'Dashboard' in ops.get('get', {}).get('tags', [])}
        self.assertEqual(paths, documented)
        self.assertEqual(len(paths), 7)
        planned = [op for ops in learning['paths'].values() for op in ops.values() if op.get('x-implementation-status') == 'planned-issue-27']
        self.assertEqual(len(planned), 6)
        for op in planned:
            params = {p['name'] for p in op['parameters']}
            self.assertTrue({'studentId', 'X-User-Role', 'X-User-Id', 'X-Student-Scope', 'from', 'to'} <= params)
        for name in ['DashboardPublicAttempt', 'DashboardAttemptDetail']:
            self.assertNotIn('draft', core['components']['schemas'][name]['properties'])
        self.assertIn('draft', core['components']['schemas']['DashboardAttempt']['properties'])
        self.assertEqual(core['components']['schemas']['DashboardMetric'], learning['components']['schemas']['DashboardMetric'])
        for path in ['/students/me/attempts', '/children/{childId}/attempts']:
            params = {p['name']: p for p in core['paths'][path]['get']['parameters']}
            self.assertEqual(params['size']['schema']['maximum'], 100)
            self.assertEqual(params['status']['schema']['enum'], ['IN_PROGRESS', 'COMPLETED'])

    def test_frontend_consumers_keep_compatible_top_level_shapes(self):
        source = (ROOT / 'frontend/web/src/data/parent/api.ts').read_text('utf-8')
        for suffix in ['summary', 'thinking-types', 'attempts']:
            self.assertIn('/' + suffix, source)
        spec = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text('utf-8'))
        props = spec['components']['schemas']['DashboardAttemptDetail']['properties']
        self.assertTrue({'attemptId', 'studentId', 'mission', 'answers', 'status', 'state', 'period'} <= props.keys())
