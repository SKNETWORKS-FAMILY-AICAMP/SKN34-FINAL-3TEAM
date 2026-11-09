"""#439 core 테마 초안 관리자 프록시·이야기 열람 프록시를 core 공개 OpenAPI와 대조한다.

learning 내부 계약(#438)이 아직 learning OpenAPI에 없으면 core ↔ 공개 OpenAPI만 맞추고,
learning OpenAPI에 `/admin/theme-drafts`·`story-views`가 생기면 core가 넘기는 경로·query·상태 값과 3자 대조한다.
"""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core'
CONTROLLER = CORE / 'learning/controller/AdminThemeDraftsController.kt'
STUDENT = CORE / 'learning/controller/WeeklyThemeController.kt'
PROXY = CORE / 'learning/service/LearningProxyService.kt'
SERVICE = CORE / 'learning/service/AdminLearningService.kt'
FILTER = CORE / 'account/controller/PublicAuthFilter.kt'
PREFIX = '/admin/theme-drafts'
STORY = '/students/{studentId}/weekly-theme/story-views'


class ThemeDraftsContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        cls.learning = yaml.safe_load((ROOT / 'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))
        cls.controller = CONTROLLER.read_text(encoding='utf-8')
        cls.service = SERVICE.read_text(encoding='utf-8')

    def core_routes(self):
        """core 메서드마다 service.themeDrafts("METHOD", draftId?, "action"?)가 만드는 learning 경로"""
        routes = set()
        for call in re.findall(r'service\.themeDrafts\(([^)]*)\)', self.controller):
            args = [a.strip() for a in call.split(',')]
            path = PREFIX
            if len(args) > 1 and args[1] == 'draftId':
                path += '/{draftId}'
                if len(args) > 2 and args[2].startswith('"'):
                    path += '/' + args[2].strip('"')
            routes.add((args[0].strip('"').lower(), path))
        return routes

    @staticmethod
    def documented(spec, prefix=PREFIX):
        return {(m, p) for p, methods in spec['paths'].items() if p.startswith(prefix)
                for m in methods if m != 'parameters'}

    def test_core_routes_match_public_contract(self):
        mapped = set()
        for method, path in re.findall(r'@(Get|Post)Mapping(?:\("([^"]*)"\))?', self.controller):
            mapped.add((method.lower(), PREFIX + (path or '')))
        self.assertEqual(len(mapped), 6)
        self.assertEqual(mapped, self.core_routes())
        self.assertEqual(self.documented(self.public), mapped)
        query = {p['name'] for p in self.public['paths'][PREFIX]['get']['parameters']}
        self.assertEqual(query, {'status', 'source', 'page', 'size'})
        for name in query:
            self.assertIn(f'"{name}"', self.controller)

    def test_filters_match_public_enums(self):
        params = {p['name']: p['schema'] for p in self.public['paths'][PREFIX]['get']['parameters']}
        for const, name in (('DRAFT_STATUSES', 'status'), ('DRAFT_SOURCES', 'source')):
            core = re.search(const + r'=setOf\(([^)]*)\)', self.controller).group(1)
            self.assertEqual([s.strip().strip('"') for s in core.split(',')], params[name]['enum'], name)

    def test_content_permission_and_audit_actions(self):
        rule = re.search(r'(path\.startsWith\("/admin/missions"\)[^>]*)-> "CONTENT"', FILTER.read_text(encoding='utf-8')).group(1)
        self.assertIn(f'path.startsWith("{PREFIX}")', rule)
        for action in ('REQUEST', 'DISCARD', 'REGENERATE', 'ADOPT'):
            self.assertIn(f'"THEME_DRAFT_{action}"', self.service)
        self.assertIn(f'"{PREFIX}"', self.service)
        for method, path in self.documented(self.public):
            operation = self.public['paths'][path][method]
            self.assertIn('CONTENT', operation['description'])
            self.assertIn('NOT_FOUND', operation['responses']['404']['description'])
            if method == 'post':
                success = next(code for code in operation['responses'] if str(code).startswith('2'))
                self.assertIn('X-Admin-Operation-Id', operation['responses'][success]['headers'])

    def test_story_view_route_kind_and_internal_path(self):
        student = STUDENT.read_text(encoding='utf-8')
        self.assertIn('@PostMapping("/api/v1/students/me/weekly-theme/story-views")', student)
        self.assertIn('post', self.public['paths']['/students/me/weekly-theme/story-views'])
        kinds = self.public['components']['schemas']['WeeklyThemeStoryViewRequest']['properties']['kind']['enum']
        proxy = PROXY.read_text(encoding='utf-8')
        core = re.search(r'STORY_KINDS = setOf\(([^)]*)\)', proxy).group(1)
        self.assertEqual([k.strip().strip('"') for k in core.split(',')], kinds)
        self.assertIn('"/students/${context.studentScope.single()}/weekly-theme/story-views", themeQuery(context)', proxy)

    def test_learning_contract_when_published(self):
        """learning #438이 OpenAPI에 경로를 올리면 core가 넘기는 경로·query·상태 값과 같아야 한다"""
        learning = self.documented(self.learning)
        if not learning:
            self.skipTest('learning #438 테마 초안 계약 미반영')
        self.assertEqual(self.core_routes(), learning)
        names = {p.get('name') for p in self.learning['paths'][PREFIX]['get']['parameters'] if 'name' in p}
        self.assertEqual(names, {'status', 'source', 'page', 'size'})
        self.assertIn('post', self.learning['paths'][STORY])


if __name__ == '__main__':
    unittest.main()
