"""테마 초안·장면 검수·이야기 열람의 core 프록시와 공개·learning OpenAPI 계약을 대조한다."""
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
VERSIONS = PREFIX + '/{draftId}/scenes/{scene}/versions'
LIST_FILTERS = {'grade', 'weekStart', 'hideDiscarded', 'comparisonPending', 'status', 'source', 'page', 'size'}
STORY = '/students/{studentId}/weekly-theme/story-views'


class ThemeDraftsContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        cls.learning = yaml.safe_load((ROOT / 'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))
        cls.controller = CONTROLLER.read_text(encoding='utf-8')
        cls.service = SERVICE.read_text(encoding='utf-8')

    def core_routes(self):
        """core 컨트롤러의 호출 인자를 learning 프록시 경로로 변환한다."""
        routes = set()
        for call in re.findall(r'service\.themeDrafts\(([^)]*)\)', self.controller):
            args = [a.strip() for a in call.split(',')]
            path = PREFIX
            if len(args) > 1 and args[1] == 'draftId':
                path += '/{draftId}'
                if len(args) > 2 and args[2].startswith('"'):
                    path += '/' + args[2].strip('"')
            routes.add((args[0].strip('"').lower(), path))
        suffixes = {'GET': '', 'PUT': '/selection', 'PATCH': '/{versionId}'}
        for method in re.findall(r'service\.sceneVersions\("([^"]+)",\s*draftId,\s*scene\.name', self.controller):
            routes.add((method.lower(), VERSIONS + suffixes[method]))
        return routes

    @staticmethod
    def documented(spec, prefix=PREFIX):
        return {(m, p) for p, methods in spec['paths'].items() if p.startswith(prefix)
                for m in methods if m != 'parameters'}

    def test_core_routes_match_public_contract(self):
        mapped = set()
        for method, path in re.findall(r'@(Get|Post|Put|Patch)Mapping(?:\("([^"]*)"\))?', self.controller):
            mapped.add((method.lower(), PREFIX + (path or '')))
        self.assertEqual(mapped, self.core_routes())
        self.assertEqual(self.documented(self.public), mapped)
        query = {p['name'] for p in self.public['paths'][PREFIX]['get']['parameters']}
        self.assertEqual(query, LIST_FILTERS)
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
        for action in ('SELECT', 'ANNOTATE'):
            self.assertIn(f'"THEME_SCENE_{action}"', self.service)
        self.assertIn('"/admin/theme-drafts/$draftId/scenes/$scene/versions"', self.service)
        self.assertIn('if (select) "$path/selection" else "$path/$versionId"', self.service)
        self.assertIn(f'"{PREFIX}"', self.service)
        for method, path in self.documented(self.public):
            operation = self.public['paths'][path][method]
            self.assertIn('CONTENT', operation['description'])
            self.assertIn('NOT_FOUND', operation['responses']['404']['description'])
            if method in {'post', 'put', 'patch'}:
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

    def test_learning_routes_and_filter_contract(self):
        learning = self.documented(self.learning)
        self.assertEqual(self.core_routes(), learning)
        params = {p['name']: p['schema'] for p in self.learning['paths'][PREFIX]['get']['parameters'] if 'name' in p}
        self.assertEqual(set(params), LIST_FILTERS)
        public = {p['name']: p['schema'] for p in self.public['paths'][PREFIX]['get']['parameters']}
        for name in ('grade', 'weekStart', 'hideDiscarded', 'comparisonPending'):
            self.assertEqual(params[name], public[name], name)
        for name in ('status', 'source'):
            internal = self.learning['components']['schemas'][params[name]['$ref'].rsplit('/', 1)[1]]
            self.assertEqual(internal['enum'], public[name]['enum'], name)
        self.assertIn('post', self.learning['paths'][STORY])

    def test_version_selection_annotation_and_week_expectations(self):
        schemas = self.public['components']['schemas']
        for name in ('ReviewSceneHistory', 'SceneSelectionRequest', 'SceneAnnotationRequest', 'DraftWeekExpectation'):
            self.assertEqual(schemas[name], self.learning['components']['schemas'][name], name)
        for spec in (self.public, self.learning):
            for method, suffix, body in (('get', '', None), ('put', '/selection', 'SceneSelectionRequest'),
                                         ('patch', '/{versionId}', 'SceneAnnotationRequest')):
                op = spec['paths'][VERSIONS + suffix][method]
                self.assertEqual(op['responses']['200']['content']['application/json']['schema']['$ref'],
                                 '#/components/schemas/ReviewSceneHistory')
                if body:
                    self.assertEqual(op['requestBody']['content']['application/json']['schema']['$ref'],
                                     '#/components/schemas/' + body)
            for action in ('adopt', 'discard'):
                op = spec['paths'][PREFIX + '/{draftId}/' + action]['post']
                self.assertEqual(op['requestBody']['content']['application/json']['schema']['$ref'],
                                 '#/components/schemas/DraftWeekExpectation')
        history = schemas['ReviewSceneHistory']
        self.assertIn('selectedVersionId', history['required'])
        self.assertEqual(history['properties']['selectedVersionId'], {'type': ['string', 'null'], 'format': 'uuid'})
        scenes = re.search(r'enum class ReviewScene\s*\{([^}]+)\}', self.controller).group(1)
        self.assertEqual(history['properties']['scene']['enum'], [s.strip() for s in scenes.split(',')])
        version = history['properties']['versions']['items']['properties']
        for field, non_null_type in (('imageUrl', 'string'), ('videoUrl', 'string'), ('motion', 'object')):
            self.assertEqual(set(version[field]['type']), {non_null_type, 'null'}, field)
        selection = schemas['SceneSelectionRequest']
        self.assertEqual(set(selection['required']), {'versionId', 'expectedVersionId'})
        self.assertEqual(selection['properties']['expectedVersionId'], history['properties']['selectedVersionId'])
        self.assertEqual(selection['properties']['expectedVersionCount']['minimum'], 1)
        self.assertEqual(schemas['SceneAnnotationRequest']['properties']['note']['maxLength'], 160)
        week = schemas['DraftWeekExpectation']
        self.assertNotIn('expectedPlannedWeek', week.get('required', []))
        self.assertEqual(week['properties']['expectedPlannedWeek'], {'type': ['string', 'null'], 'format': 'date'})


if __name__ == '__main__':
    unittest.main()
