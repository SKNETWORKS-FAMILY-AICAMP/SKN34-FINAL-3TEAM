"""#387 core 주간 테마 프록시·시도 context 계약을 core 컨트롤러와 대조한다.

core 공개 OpenAPI ↔ core 컨트롤러, core가 learning에 넘기는 내부 경로 ↔ learning OpenAPI(#385)를 함께 맞춘다(3자 대조).
learning OpenAPI ↔ learning 컨트롤러는 test_record_exists_openapi가 대조한다.
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
THEME = ROOT / 'backend/learning-service/src/main/kotlin/com/sagomungchi/learning/theme'


class WeeklyThemeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        cls.admin = ADMIN.read_text(encoding='utf-8')
        cls.student = STUDENT.read_text(encoding='utf-8')
        cls.learning = yaml.safe_load((ROOT / 'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))

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
        self.assertEqual(query, {'grade', 'weekStart', 'status', 'page', 'size'})
        grades = re.search(r'GRADES=setOf\(([^)]*)\)', self.admin).group(1)
        enum = next(p for p in self.spec['paths']['/admin/weekly-themes']['get']['parameters'] if p['name'] == 'grade')['schema']['enum']
        self.assertEqual([g.strip().strip('"') for g in grades.split(',')], enum)
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
        # 날짜는 클라이언트 값이 아니라 core KST 오늘(열람 적립 #389은 같은 날짜로 주 시작일을 정함)
        self.assertIn('date: LocalDate = entitlements.today()', proxy)
        # #485: 일요일 허용 값(상품 판단)을 learning에 함께 넘긴다
        self.assertIn('"grade=$grade&date=$date&sundayTheme=$sunday"', proxy)
        self.assertIn('&sundayTheme=${permit.sundayTheme}', proxy)

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

    def test_core_admin_proxy_routes_match_learning_contract(self):
        """core 메서드마다 service.weeklyThemes("METHOD", themeId?, "action"?)가 만드는 learning 경로 (#385)"""
        routes = set()
        for call in re.findall(r'service\.weeklyThemes\(([^)]*)\)', self.admin):
            args = [a.strip() for a in call.split(',')]
            path = '/admin/weekly-themes'
            if len(args) > 1 and args[1] == 'themeId':
                path += '/{themeId}'
                if len(args) > 2 and args[2].startswith('"'):
                    path += '/' + args[2].strip('"')
            routes.add((args[0].strip('"').lower(), path))
        documented = {(m, p) for p, methods in self.learning['paths'].items() if p.startswith('/admin/weekly-themes') for m in methods}
        self.assertEqual(len(documented), 7)
        self.assertEqual(routes, documented)
        params = {p.get('name') for p in self.learning['paths']['/admin/weekly-themes']['get']['parameters'] if 'name' in p}
        self.assertEqual(params, {'grade', 'weekStart', 'status', 'page', 'size'})

    def test_core_student_internal_paths_are_in_learning_contract(self):
        # #438 학년별 테마: learning은 grade를 받고, core 반영 전까지 core가 보내는 gradeBand도 받는다(사용 중단 예정)
        for method, path in (('get', '/students/{studentId}/weekly-theme'), ('post', '/students/{studentId}/weekly-theme/review-views')):
            params = {self.parameter(p).get('name'): self.parameter(p) for p in self.learning['paths'][path][method]['parameters']}
            self.assertTrue({'grade', 'gradeBand', 'date'} <= set(params), path)
            self.assertFalse(params['grade'].get('required', False), path)
            self.assertTrue(params['gradeBand'].get('deprecated'), path)

    def test_learning_theme_paths_declare_sunday_query(self):
        # #484: core가 시도 시작·조회·열람 3종에 붙이는 sundayTheme을 learning 계약이 모두 선언(정답 고르기도 같은 쿼리)
        for method, path in (
            ('post', '/missions/{missionId}/attempts'),
            ('get', '/students/{studentId}/weekly-theme'),
            ('post', '/students/{studentId}/weekly-theme/review-views'),
            ('post', '/students/{studentId}/weekly-theme/story-views'),
            ('post', '/students/{studentId}/weekly-theme/answer-picks'),
        ):
            params = {self.parameter(p).get('name'): self.parameter(p) for p in self.learning['paths'][path][method]['parameters']}
            self.assertIn('sundayTheme', params, path)
            self.assertFalse(params['sundayTheme'].get('required', False), path)

    def test_learning_theme_grades_match_domain(self):
        # learning OpenAPI ThemeGrade enum = 도메인 ThemeGrade (#438)
        calendar = (THEME / 'domain/ThemeCalendar.kt').read_text(encoding='utf-8')
        domain = re.search(r'enum class ThemeGrade\(val grade: Int\) \{\s*([^;]+);', calendar).group(1)
        self.assertEqual(re.findall(r'(G\d)\(\d\)', domain), self.learning['components']['schemas']['ThemeGrade']['enum'])

    def test_learning_start_context_and_publish_codes(self):
        learning = self.learning['components']['schemas']['AttemptStartRequest']['properties']['context']['enum']
        self.assertEqual(learning, self.spec['components']['schemas']['AttemptStartRequest']['properties']['context']['enum'])
        codes = self.learning['components']['schemas']['ThemePublishError']['properties']['code']['enum']
        domain = (THEME / 'domain/WeeklyTheme.kt').read_text(encoding='utf-8') + (THEME / 'service/WeeklyThemeAdminService.kt').read_text(encoding='utf-8')
        self.assertEqual(set(codes), set(re.findall(r'ThemePublishError\("([A-Z_]+)"', domain)))

    def parameter(self, item):
        if '$ref' not in item:
            return item
        return self.learning['components']['parameters'][item['$ref'].rsplit('/', 1)[1]]


if __name__ == '__main__':
    unittest.main()
