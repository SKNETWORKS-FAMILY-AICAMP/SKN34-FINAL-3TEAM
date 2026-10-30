"""#146 core 신고 지원 클라이언트(#46 LearningSupportClient)가 부르는 경로·읽는 칸과 learning 신고 지원 조회 계약을 대조한다.

learning OpenAPI는 test_record_exists_openapi가 learning 컨트롤러와 대조하므로, 여기서 core ↔ OpenAPI를 맞추면 core ↔ learning 컨트롤러가 이어진다.
"""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/support/client/LearningSupportClient.kt'
CORE_SERVICE = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core/support/service/SupportService.kt'


class SupportLookupContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / 'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))
        cls.core = CORE.read_text(encoding='utf-8')
        cls.core_service = CORE_SERVICE.read_text(encoding='utf-8')
        cls.schemas = cls.spec['components']['schemas']

    def test_core_support_paths_are_learning_paths(self):
        """core가 GET으로 부르는 /support/... 경로가 learning OpenAPI에 같은 모양으로 있음"""
        called = {re.sub(r'\$\w+', '{}', p) for p in re.findall(r'exchange\("GET", "(/support/[^"]+)"\)', self.core)}
        documented = {re.sub(r'\{\w+\}', '{}', p) for p, methods in self.spec['paths'].items() if p.startswith('/support/') and 'get' in methods}
        self.assertEqual(called, {'/support/targets/{}/{}', '/support/attempts/{}'})
        self.assertEqual(called, documented)

    def test_target_types_cover_core_calls(self):
        """core가 learning에 묻는 대상 유형(JUDGMENT·FOLLOWUP·ATTEMPT)이 모두 허용 값"""
        types = next(p for p in self.spec['paths']['/support/targets/{targetType}/{targetId}']['get']['parameters']
                     if p.get('name') == 'targetType')['schema']['enum']
        core_types = set(re.search(r'"JUDGMENT","FOLLOWUP","ATTEMPT"', self.core_service).group(0).replace('"', '').split(','))
        self.assertEqual(set(types), core_types)

    def test_fields_core_reads_are_documented(self):
        """core가 읽는 칸: target의 studentId·attemptId·previousResult, 원문의 studentId·attemptId·answers[answerId·version·text·feedback]"""
        target = self.schemas['SupportTarget']
        self.assertEqual(set(target['required']), {'studentId', 'attemptId'})
        self.assertTrue({'judgmentId', 'previousResult'} <= set(target['properties']))
        self.assertEqual(set(target['properties']['previousResult']['enum']), {'CORRECT', 'PARTIAL', 'RETHINK', 'HELD'})
        original = self.schemas['SupportOriginal']
        self.assertEqual(set(original['required']), {'studentId', 'attemptId', 'answers'})
        answer = original['properties']['answers']['items']
        self.assertEqual(set(answer['required']), {'answerId', 'version', 'text', 'feedback'})
        self.assertFalse(answer.get('additionalProperties', True))
        for field in ('answerId', 'version', 'text', 'feedback'):
            self.assertIn(f'"{field}"', self.core)

    def test_feedback_judgment_has_id(self):
        """피드백 판정에 신고 대상 judgmentId (#146, core 합의 a)"""
        self.assertIn('judgmentId', self.schemas['Judgment']['required'])


if __name__ == '__main__':
    unittest.main()
