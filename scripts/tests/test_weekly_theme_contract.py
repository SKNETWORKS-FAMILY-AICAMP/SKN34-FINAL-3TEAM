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
PLANNER = '/admin/weekly-themes/planner'


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
        self.assertTrue({('get', PLANNER), ('put', PLANNER)} <= routes)
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
        self.assertIn(f'"{PLANNER}"', service)
        self.assertIn('"THEME_DRAFT_PLAN"', service)

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
        for method in re.findall(r'service\.weeklyPlanner\("([^"]+)"', self.admin):
            routes.add((method.lower(), PLANNER))
        documented = {(m, p) for p, methods in self.learning['paths'].items() if p.startswith('/admin/weekly-themes')
                      for m in methods if m != 'parameters'}
        self.assertEqual(routes, documented)
        params = {p.get('name') for p in self.learning['paths']['/admin/weekly-themes']['get']['parameters'] if 'name' in p}
        self.assertEqual(params, {'grade', 'weekStart', 'status', 'page', 'size'})

    def test_review_and_unpublish_match_the_version_opened_by_the_admin(self):
        for spec in (self.spec, self.learning):
            for action, version in [('review-request', 'expectedVersion'), ('unpublish', 'expectedPublishedVersion')]:
                operation = spec['paths']['/admin/weekly-themes/{themeId}/' + action]['post']
                body = operation['requestBody']['content']['application/json']['schema']
                self.assertEqual(body['properties'][version], {'type': 'integer', 'minimum': 1})
                self.assertNotIn(version, body.get('required', []))
                self.assertIn('409', operation['responses'])

    def test_four_week_board_and_planning_expectations(self):
        schemas = self.spec['components']['schemas']
        for name in ('PlannerDraft', 'WeekBoard', 'WeekPlanChange', 'WeekPlanResult', 'FinalPublicationRequest'):
            self.assertEqual(schemas[name], self.learning['components']['schemas'][name], name)
        for spec in (self.spec, self.learning):
            get = spec['paths'][PLANNER]['get']
            put = spec['paths'][PLANNER]['put']
            query = {p['name'] for p in get['parameters'] if p.get('in') == 'query' and p.get('required')}
            self.assertEqual(query, {'grade', 'weekStart'})
            self.assertEqual(get['responses']['200']['content']['application/json']['schema']['$ref'],
                             '#/components/schemas/WeekBoard')
            self.assertEqual(put['requestBody']['content']['application/json']['schema']['$ref'],
                             '#/components/schemas/WeekPlanChange')
            self.assertEqual(put['responses']['200']['content']['application/json']['schema']['$ref'],
                             '#/components/schemas/WeekPlanResult')
            publish = spec['paths']['/admin/weekly-themes/{themeId}/publish']['post']
            self.assertEqual(publish['requestBody']['content']['application/json']['schema']['$ref'],
                             '#/components/schemas/FinalPublicationRequest')

        board = schemas['WeekBoard']
        self.assertEqual(set(board['required']), {'grade', 'weekStart', 'weeks', 'candidates'})
        weeks = board['properties']['weeks']
        self.assertEqual((weeks['minItems'], weeks['maxItems']), (4, 4))
        slot = weeks['items']
        self.assertEqual(set(slot['required']), {'weekStart', 'locked', 'planned', 'themes'})
        planned = {'$ref': '#/components/schemas/PlannerDraft'}
        self.assertCountEqual(slot['properties']['planned']['anyOf'], [planned, {'type': 'null'}])
        self.assertEqual(board['properties']['candidates']['items'], planned)
        self.assertEqual(schemas['PlannerDraft']['properties']['generationWeek'], {'type': 'string', 'format': 'date'})

        for name, field, fmt in (('PlannerDraft', 'plannedWeek', 'date'), ('WeekPlanChange', 'expectedWeek', 'date'),
                                 ('WeekPlanChange', 'targetWeek', 'date'), ('WeekPlanChange', 'expectedTargetDraftId', 'uuid'),
                                 ('WeekPlanResult', 'plannedWeek', 'date'), ('WeekPlanResult', 'displacedDraftId', 'uuid')):
            with self.subTest(schema=name, field=field):
                self.assertIn(field, schemas[name]['required'])
                self.assertEqual(schemas[name]['properties'][field], {'type': ['string', 'null'], 'format': fmt})
        final = schemas['FinalPublicationRequest']
        self.assertEqual(final['properties']['expectedVersion']['minimum'], 1)
        self.assertNotIn('expectedPlannedDraftId', final.get('required', []))
        self.assertEqual(final['properties']['expectedPlannedDraftId']['type'], ['string', 'null'])
        self.assertEqual(final['properties']['expectedPlannedDraftId']['format'], 'uuid')

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

    def test_answer_pick_route_body_and_internal_path(self):
        # #550: core는 {pick}만 확인해 learning answer-picks에 다른 열람 기록과 같은 학년·날짜·sundayTheme 질의로 넘긴다
        self.assertIn('@PostMapping("/api/v1/students/me/weekly-theme/answer-picks")', self.student)
        operation = self.spec['paths']['/students/me/weekly-theme/answer-picks']['post']
        self.assertTrue({'200', '400', '409'}.issubset(operation['responses']))
        self.assertIn('THEME_PICK_NOT_ALLOWED', operation['responses']['409']['description'])
        request = self.spec['components']['schemas']['WeeklyThemeAnswerPickRequest']
        self.assertEqual((request['required'], request['additionalProperties']), (['pick'], False))
        result = self.spec['components']['schemas']['WeeklyThemeAnswerPickResult']
        self.assertEqual(result['properties']['ending']['enum'], ['NOT_ENDED', 'ENDED'])
        proxy = PROXY.read_text(encoding='utf-8')
        self.assertIn('"/students/${context.studentScope.single()}/weekly-theme/answer-picks", themeQuery(context)', proxy)
        self.assertIn('mapOf("pick" to pick)', proxy)
        community = (CORE / 'community/client/CommunityClient.kt').read_text(encoding='utf-8')
        self.assertIn('(403 to "COMMUNITY_LOCKED_UNTIL_ENDING")', community)

    def test_answer_pick_learning_contract_when_published(self):
        """learning #484가 OpenAPI에 answer-picks를 올리면 core가 넘기는 경로·query·코드와 같아야 한다"""
        path = '/students/{studentId}/weekly-theme/answer-picks'
        if path not in self.learning['paths']:
            self.skipTest('learning #484 정답 고르기 계약 미반영')
        operation = self.learning['paths'][path]['post']
        names = {self.parameter(p).get('name') for p in operation.get('parameters', [])}
        self.assertTrue({'grade', 'date', 'sundayTheme'} <= names, names)
        self.assertIn('THEME_PICK_NOT_ALLOWED', yaml.safe_dump(operation, allow_unicode=True))

    def test_clue_features_are_optional_and_match_domain(self):
        """#647 단서 근거: ai 응답 theme.features·days[].clueFeature는 선택 칸이고, learning 학생·관리자·초안 응답과 관리자 본문,
        Kotlin 칸 이름이 같다(기존 칸은 바뀌지 않음)"""
        ai = yaml.safe_load((ROOT / 'contracts/openapi/ai-service.yaml').read_text(encoding='utf-8'))['components']['schemas']
        self.assertNotIn('features', ai['Theme']['required'])
        self.assertNotIn('clueFeature', ai['ThemeDay']['required'])
        self.assertEqual(ai['ThemeFeature']['required'], ['name', 'values'])
        self.assertEqual(ai['ThemeFeatureValue']['required'], ['candidate', 'value'])
        schemas = self.learning['components']['schemas']
        day = schemas['WeeklyTheme']['properties']['days']['items']['properties']
        self.assertEqual(day['clueFacts']['items']['$ref'], '#/components/schemas/ThemeFeatureValue')
        self.assertEqual(day['clueFeature']['type'], ['string', 'null'])
        self.assertEqual(schemas['WeeklyTheme']['properties']['features']['type'], ['array', 'null'])
        self.assertIn('clueFeature', schemas['ThemeDayMission']['properties'])
        self.assertNotIn('clueFeature', schemas['ThemeDayMission']['required'])
        self.assertNotIn('features', schemas['AdminWeeklyThemeRequest']['required'])
        self.assertIn('features', schemas['AdminWeeklyTheme']['properties'])
        self.assertIn('clueFeature', schemas['AdminThemeDay']['properties'])
        self.assertNotIn('features', schemas['GeneratedTheme']['required'])
        views = (THEME / 'domain/ThemeViews.kt').read_text(encoding='utf-8')
        for name in ('val clueFeature: String? = null', 'val clueFacts: List<ThemeFeatureValue>? = null',
                     'val features: List<ThemeFeature>? = null'):
            self.assertIn(name, views)
        domain = (THEME / 'domain/WeeklyTheme.kt').read_text(encoding='utf-8')
        self.assertIn('data class ThemeFeature(val name: String, val values: List<ThemeFeatureValue>)', domain)
        self.assertIn('data class ThemeFeatureValue(val candidate: String, val value: String)', domain)
        # 학생 응답을 그대로 전달하는 core 설명에 새 칸이 적혀 있음(코드 변경 없음)
        self.assertIn('clueFacts', yaml.safe_dump(self.spec, allow_unicode=True))

    def parameter(self, item):
        if '$ref' not in item:
            return item
        return self.learning['components']['parameters'][item['$ref'].rsplit('/', 1)[1]]


if __name__ == '__main__':
    unittest.main()
