"""#656 계약 소항목: 내부 경로 servers 재정의, 판정 요소 sourceType과 web 검사 일치."""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    return yaml.safe_load((ROOT / 'contracts/openapi' / name).read_text(encoding='utf-8'))


class ContractAlignment656Test(unittest.TestCase):
    def test_core_internal_paths_are_served_from_root(self):
        # 전역 servers는 /api/v1이라 /internal 경로는 경로나 operation에서 / 로 재정의해야 실제 경로와 같다.
        api = load('core-service.yaml')
        internal = {p: v for p, v in api['paths'].items() if p.startswith('/internal/')}
        self.assertIn('/internal/deletion-requests/{deletionRequestId}/completions', internal)
        for path, item in internal.items():
            for method, op in item.items():
                if method == 'servers' or not isinstance(op, dict):
                    continue
                self.assertEqual(op.get('servers', item.get('servers')), [{'url': '/'}], (path, method))

    def test_judgment_element_source_type_excludes_record_and_matches_web(self):
        # RECORD는 기록 지표(Metric) 출처라 판정 요소에는 오지 않는다. learning 공급·core 중계·web 검사가 같은 집합이어야 한다.
        expected = ['RULE', 'ANSWER_KEY', 'AI_OBSERVATION', None]
        learning = load('learning-service.yaml')['components']['schemas']
        core = load('core-service.yaml')['components']['schemas']
        self.assertEqual(learning['Element']['properties']['sourceType']['enum'], expected)
        self.assertEqual(core['DashboardElement']['properties']['sourceType']['enum'], expected)
        # 기록 지표는 계속 RECORD
        self.assertEqual(learning['Metric']['properties']['sourceType']['enum'], ['RECORD'])
        source = (ROOT / 'frontend/web/src/data/classroom/apiGateway.ts').read_text(encoding='utf-8')
        match = re.search(r"j\.elements\.some\(\(e\) => !\[([^\]]*)\]\.includes\(object\(e\)\.sourceType", source)
        self.assertIsNotNone(match)
        web = [None if v.strip() == 'null' else v.strip().strip("'") for v in match.group(1).split(',')]
        self.assertEqual(sorted(web, key=str), sorted(expected, key=str))


if __name__ == '__main__':
    unittest.main()
