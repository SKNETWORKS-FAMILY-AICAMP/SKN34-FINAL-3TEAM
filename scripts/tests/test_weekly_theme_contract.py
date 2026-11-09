"""#387 core 주간 테마 프록시·시도 context 계약을 core 컨트롤러와 대조한다.

learning 주간 테마 API(#385)는 아직 learning OpenAPI("구현된 경로만")에 없으므로, 여기서는 core 공개 OpenAPI ↔ core 컨트롤러와
core가 learning에 넘기는 내부 경로(api-spec 4.1)만 맞춘다. learning이 경로를 올리면 test_admin_mission_drafts_contract처럼 3자 대조로 넓힌다.
"""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core'
ADMIN = CORE / 'learning/controller/AdminWeeklyThemesController.kt'
STUDENT = CORE / 'learning/controller/WeeklyThemeController.kt'
PROXY = CORE / 'learning/service/LearningProxyService.kt'
ADMIN_SERVICE = CORE / 'learning/service/AdminLearningService.kt'
FILTER = CORE / 'account/controller/PublicAuthFilter.kt'


class WeeklyThemeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        cls.admin = ADMIN.read_text(encoding='utf-8')
        cls.student = STUDENT.read_text(encoding='utf-8')

    def documented(self, prefix):
        return {(m, p) for p, methods in self.spec['paths'].items() if p.startswith(prefix)
                for m in methods if m != 'parameters'}

    def test_admin_routes_match_public_contract(self):
        routes = set()
        for method, path in re.findall(r'@(Get|Post|Put)Mapping(?:\("([^"]*)"\))?', self.admin):
            routes.add((method.lower(), '/admin/weekly-themes' + (path or '')))
        self.assertEqual(len(routes), 7)
        self.assertEqual(routes, self.documented('/admin/weekly-themes'))
        query = {p['name'] for p in self.spec['paths']['/admin/weekly-themes']['get']['parameters']}
        self.assertEqual(query, {'gradeBand', 'weekStart', 'status', 'page', 'size'})
        self.assertIn('path.startsWith("/admin/weekly-themes") -> "CONTENT"', FILTER.read_text(encoding='utf-8'))
        service = ADMIN_SERVICE.read_text(encoding='utf-8')
        for action in ('CREATE', 'UPDATE'):
            self.assertIn(f'"WEEKLY_THEME_{action}"', service)
        self.assertIn('"WEEKLY_THEME_${action!!', service)
        self.assertIn('"/admin/weekly-themes"', service)

    def test_student_routes_and_internal_paths(self):
        routes = {(m.lower(), p.removeprefix('/api/v1')) for m, p in re.findall(r'@(Get|Post)Mapping\("([^"]+)"\)', self.student)}
        self.assertEqual(routes, self.documented('/students/me/weekly-theme'))
        self.assertEqual({op['tags'][0] for _, methods in self.spec['paths'].items() for op in methods.values()
                          if isinstance(op, dict) and 'WeeklyTheme' in op.get('tags', [])}, {'WeeklyTheme'})
        proxy = PROXY.read_text(encoding='utf-8')
        self.assertIn('"/students/${context.studentScope.single()}/weekly-theme"', proxy)
        self.assertIn('"/students/${context.studentScope.single()}/weekly-theme/review-views"', proxy)
        self.assertIn('"gradeBand=$band&date=${entitlements.today()}"', proxy)

    def test_free_mission_limit_lives_in_usage_and_policy_in_entitlement(self):
        usage = (CORE / 'usage/service/MissionUsageService.kt').read_text(encoding='utf-8')
        self.assertIn('class MissionUsageService', usage)
        self.assertIn('"USAGE_LIMIT_REACHED"', usage)
        entitlement = (CORE / 'payment/service/ProductEntitlementService.kt').read_text(encoding='utf-8')
        self.assertIn('missionUsage.requireAvailable', entitlement)
        self.assertIn('features["extraMissions"]', entitlement)
        self.assertFalse((CORE / 'payment/repository/MissionDailyUsageRepository.kt').exists())
        self.assertIn('MissionUsageService', (CORE / 'guardianship/service/ChildManagementService.kt').read_text(encoding='utf-8'))

    def test_attempt_context_contract(self):
        schema = self.spec['components']['schemas']['AttemptStartRequest']
        self.assertEqual(schema['properties']['context']['enum'], ['THEME_DAY', 'THEME_REVIEW', 'EXTRA', None])
        self.assertFalse(schema['additionalProperties'])
        responses = self.spec['paths']['/missions/{missionId}/attempts']['post']['responses']
        self.assertTrue({'200', '201', '400', '403', '409', '429'}.issubset(responses))
        controller = (CORE / 'learning/controller/LearningController.kt').read_text(encoding='utf-8')
        self.assertIn('setOf("THEME_DAY", "THEME_REVIEW", "EXTRA")', controller)
        self.assertIn('return "EXTRA"', controller)


if __name__ == '__main__':
    unittest.main()
