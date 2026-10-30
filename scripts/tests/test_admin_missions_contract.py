"""#145 core 관리자 미션 프록시(#47·#126)가 넘기는 경로와 learning 관리자 미션 계약을 대조한다.

learning OpenAPI는 test_record_exists_openapi가 learning 컨트롤러와 대조하므로, 여기서 core ↔ OpenAPI를 맞추면 core ↔ learning 컨트롤러가 이어진다.
"""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/controller/AdminMissionsController.kt'
CORE_SERVICE = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/service/AdminLearningService.kt'


class AdminMissionsContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / 'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))
        cls.core = CORE.read_text(encoding='utf-8')
        cls.core_service = CORE_SERVICE.read_text(encoding='utf-8')

    def core_routes(self):
        """core 메서드마다 service.missions("METHOD", missionId?, "action"?)가 만드는 learning 경로"""
        routes = set()
        for call in re.findall(r'service\.missions\(([^)]*)\)', self.core):
            args = [a.strip() for a in call.split(',')]
            method = args[0].strip('"').lower()
            path = '/admin/missions'
            if len(args) > 1 and args[1] == 'missionId':
                path += '/{missionId}'
                if len(args) > 2 and args[2].startswith('"'):
                    path += '/' + args[2].strip('"')
            routes.add((method, path))
        return routes

    def test_core_proxy_routes_match_learning_contract(self):
        documented = {(m, p) for p, methods in self.spec['paths'].items() if p.startswith('/admin/missions') for m in methods}
        self.assertEqual(len(documented), 10)
        self.assertEqual(self.core_routes(), documented)

    def test_core_filters_are_the_documented_list_query(self):
        params = {p.get('name') for p in self.spec['paths']['/admin/missions']['get']['parameters'] if 'name' in p}
        self.assertTrue({'status', 'grade', 'thinkingType', 'page', 'size'} <= params)
        for name in ('status', 'grade', 'thinkingType', 'page', 'size'):
            self.assertIn(f'"{name}"', self.core)

    def test_publish_incomplete_codes_pass_core_filter(self):
        """core 프록시는 missingFields 중 영문 경로 모양만 통과시키므로 learning 코드가 모두 그 모양이어야 한다"""
        pattern = re.search(r'Regex\("([^"]+)"\)', self.core_service).group(1).replace('\\\\', '\\')
        schema = self.spec['paths']['/admin/missions/{missionId}/publish']['post']['responses']['422']
        codes = schema['content']['application/problem+json']['schema']['allOf'][1]['properties']['missingFields']['items']['enum']
        self.assertTrue(codes)
        for code in codes:
            self.assertRegex(code, '^' + pattern + '$')


if __name__ == '__main__':
    unittest.main()
