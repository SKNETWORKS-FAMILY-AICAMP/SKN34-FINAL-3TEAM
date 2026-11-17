"""친구 방 구경(#708)의 core 소비자와 learning 작성자 확인(#707) 제공자 계약이 같은지 대조한다.

core 통합 시험은 learning을 가짜 서버로 두므로, 가짜 서버가 흉내 내는 경로·질의·응답 칸·오류 코드가
learning OpenAPI·컨트롤러와 같아야 시험이 실제 계약을 확인한다.
"""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'backend/core-service/src'
LEARNING = ROOT / 'backend/learning-service/src/main/kotlin/com/sagomungchi/learning'
PATH = '/community/posts/{postId}/author'


class FriendRoomContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.learning = yaml.safe_load((ROOT / 'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))
        cls.core = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        cls.client = (CORE / 'main/kotlin/com/sagomungchi/core/community/client/CommunityClient.kt').read_text(encoding='utf-8')
        cls.stub = (CORE / 'test/kotlin/com/sagomungchi/core/community/FriendRoomIntegrationTest.kt').read_text(encoding='utf-8')

    def parameter(self, node):
        if '$ref' in node:
            return self.learning['components']['parameters'][node['$ref'].rsplit('/', 1)[1]]
        return node

    def test_learning_publishes_author_check(self):
        operation = self.learning['paths'][PATH]['get']
        params = [self.parameter(p) for p in operation['parameters']]
        self.assertIn('viewerStudentId', {p.get('name') for p in params})
        roles = [p for p in params if p.get('name') == 'X-User-Role']
        self.assertEqual(['STUDENT'], [r['schema'].get('const') or r['schema'].get('enum', [None])[0] for r in roles])
        body = operation['responses']['200']['content']['application/json']['schema']
        self.assertEqual({'postId', 'studentId'}, set(body['properties']))
        self.assertFalse(body.get('additionalProperties', True))
        self.assertEqual({'403', '404', '409'}, {s for s in operation['responses'] if s in {'403', '404', '409'}})
        controller = (LEARNING / 'community/controller/CommunityController.kt').read_text(encoding='utf-8')
        self.assertIn('@GetMapping("/internal/community/posts/{postId}/author")', controller)

    def test_core_client_calls_the_same_path_as_viewer(self):
        self.assertIn('"/community/posts/$postId/author", "viewerStudentId=$viewer"', self.client)
        self.assertIn('acting("STUDENT", viewerUser, viewer)', self.client)
        for code in ('COMMUNITY_LOCKED', 'COMMUNITY_LOCKED_UNTIL_ENDING', 'COMMUNITY_POST_NOT_FOUND', 'COMMUNITY_OWN_POST'):
            self.assertIn(f'"{code}")', self.client)

    def test_core_stub_mimics_the_learning_contract(self):
        self.assertIn('Regex("/internal/community/posts/[^/]+/author")', self.stub)
        self.assertIn('substringAfter("viewerStudentId=")', self.stub)
        self.assertIn('ok(mapOf("postId" to post, "studentId" to who))', self.stub)

    def test_public_room_hides_identifiers(self):
        operation = self.core['paths']['/community-posts/{postId}/room']['get']
        self.assertEqual(['Community'], operation['tags'])
        room = self.core['components']['schemas']['FriendRoom']

        def names(schema):
            found = set()
            for key, value in schema.get('properties', {}).items():
                found.add(key)
                found |= names(value.get('items', value))
            return found

        self.assertFalse(names(room) & {'studentId', 'postId', 'themeId', 'weekStart', 'attemptId'})


if __name__ == '__main__':
    unittest.main()
