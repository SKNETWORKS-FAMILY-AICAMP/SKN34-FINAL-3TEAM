"""#355 core 성취기준 표·미션 초안 프록시가 넘기는 경로와 learning 계약(#353)을 대조한다.

learning OpenAPI는 test_record_exists_openapi가 learning 컨트롤러와 대조하므로, 여기서 core ↔ learning OpenAPI를 맞추면
core ↔ learning 컨트롤러가 이어진다(test_admin_missions_contract와 같은 방식).
"""
from pathlib import Path
import json
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/controller/AdminMissionDraftsController.kt'
CORE_SERVICE = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/service/AdminLearningService.kt'
FILTER = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/account/controller/PublicAuthFilter.kt'
PREFIXES = ('/admin/achievement-standards', '/admin/mission-drafts')


class AdminMissionDraftsContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.learning = yaml.safe_load((ROOT / 'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))
        cls.public = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        cls.core = CORE.read_text(encoding='utf-8')
        cls.core_service = CORE_SERVICE.read_text(encoding='utf-8')

    def core_routes(self):
        """core 메서드마다 service.missionDrafts("METHOD", draftId?, "action"?)·achievementStandards가 만드는 learning 경로"""
        routes = set()
        for call in re.findall(r'service\.missionDrafts\(([^)]*)\)', self.core):
            args = [a.strip() for a in call.split(',')]
            path = '/admin/mission-drafts'
            if len(args) > 1 and args[1] == 'draftId':
                path += '/{draftId}'
                if len(args) > 2 and args[2].startswith('"'):
                    path += '/' + args[2].strip('"')
            routes.add((args[0].strip('"').lower(), path))
        if 'service.achievementStandards(' in self.core:
            routes.add(('get', '/admin/achievement-standards'))
        return routes

    @staticmethod
    def documented(spec):
        return {(m, p) for p, methods in spec['paths'].items() if p.startswith(PREFIXES)
                for m in methods if m != 'parameters'}

    def test_core_proxy_routes_match_learning_and_public_contracts(self):
        learning = self.documented(self.learning)
        self.assertEqual(len(learning), 6)
        self.assertEqual(self.core_routes(), learning)
        self.assertEqual(self.documented(self.public), learning)

    def test_core_forwards_only_documented_query_names(self):
        for path, names in (('/admin/achievement-standards', {'subject', 'gradeBand', 'q', 'page', 'size'}),
                            ('/admin/mission-drafts', {'status', 'page', 'size'})):
            documented = {p['name'] for p in self.learning['paths'][path]['get']['parameters'] if 'name' in p}
            self.assertEqual(documented, names)
            public = {p['name'] for p in self.public['paths'][path]['get']['parameters'] if 'name' in p}
            self.assertEqual(public, names)
            for name in names:
                self.assertIn(f'"{name}"', self.core)

    def test_core_draft_status_filter_matches_learning(self):
        schema = next(p for p in self.learning['paths']['/admin/mission-drafts']['get']['parameters']
                      if p.get('name') == 'status')['schema']
        statuses = self.learning['components']['schemas'][schema['$ref'].rsplit('/', 1)[1]]['enum']
        core = re.search(r'DRAFT_STATUSES=setOf\(([^)]*)\)', self.core).group(1)
        self.assertEqual([s.strip().strip('"') for s in core.split(',')], statuses)
        public = next(p for p in self.public['paths']['/admin/mission-drafts']['get']['parameters']
                      if p.get('name') == 'status')['schema']['enum']
        self.assertEqual(public, statuses)

    def test_learning_error_codes_pass_core_filter(self):
        """learning 초안 경로 오류 코드(api-spec 4.1)는 core가 그대로 넘기는 목록 안에 있어야 한다"""
        allowed = set(re.findall(r'"([A-Z_]+)"', re.search(r'allowedCodes = setOf\(([^)]*)\)', self.core_service).group(1)))
        for code in ('VALIDATION_FAILED', 'FORBIDDEN', 'NOT_FOUND', 'CONFLICT'):
            self.assertIn(code, allowed)

    def test_permission_is_content(self):
        text = FILTER.read_text(encoding='utf-8')
        rule = re.search(r'(path\.startsWith\("/admin/missions"\)[^>]*)-> "CONTENT"', text).group(1)
        for prefix in PREFIXES:
            self.assertIn(f'path.startsWith("{prefix}")', rule)

    def test_public_operations_document_audit_and_not_found(self):
        for method, path in self.documented(self.public):
            operation = self.public['paths'][path][method]
            self.assertIn('CONTENT', operation['description'])
            self.assertIn('NOT_FOUND', operation['responses']['404']['description'])
            self.assertIn('ADMIN_MISSIONS_UNAVAILABLE', operation['responses']['503']['description'])
            if method == 'post':
                success = next(code for code in operation['responses'] if str(code).startswith('2'))
                self.assertIn('X-Admin-Operation-Id', operation['responses'][success]['headers'])
                self.assertIn('MISSION_AUDIT_UNAVAILABLE', operation['description'])


class CallTypeListTest(unittest.TestCase):
    """LLM 호출 종류는 이벤트 스키마·core enum·core CHECK·ERD·core OpenAPI와 ai·scoring 발행 목록이 같아야 한다 (#355)"""

    def test_every_call_type_list_is_the_same(self):
        schema = json.loads((ROOT / 'contracts/events/llm.usage.recorded.v1.schema.json').read_text(encoding='utf-8'))
        expected = schema['properties']['callType']['enum']
        self.assertIn('MISSION_DRAFT', expected)
        public = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        enum = (ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/usage/domain/UsageSummary.kt').read_text(encoding='utf-8')
        migrations = sorted((ROOT / 'backend/core-service/src/main/resources/db/migration').glob('V*__*.sql'),
                            key=lambda p: int(p.name[1:].split('__')[0]))
        latest = [m for m in migrations if 'ck_llm_usage_call_type' in m.read_text(encoding='utf-8')][-1]
        check = re.search(r'ADD CONSTRAINT ck_llm_usage_call_type CHECK \(call_type IN \(([^)]*)\)', latest.read_text(encoding='utf-8'))
        erd = (ROOT / 'docs/design/erd.md').read_text(encoding='utf-8')
        lists = {
            'openapi': public['components']['schemas']['CallType']['enum'],
            'enum': [v.strip() for v in re.search(r'enum class CallType \{([^}]*)\}', enum).group(1).split(',')],
            'check': re.findall(r"'([A-Z0-9_]+)'", check.group(1)),
            'erd': re.search(r'varchar call_type "([^"]*)"', erd).group(1).split('|'),
        }
        for service in ('ai', 'scoring'):
            text = (ROOT / f'backend/{service}-service/app/messaging/publisher.py').read_text(encoding='utf-8')
            lists[service] = re.findall(r'"([A-Z0-9_]+)"', re.search(r'CallType = Literal\[([^\]]*)\]', text).group(1))
        for name, values in lists.items():
            self.assertEqual(values, expected, name)


if __name__ == '__main__':
    unittest.main()
