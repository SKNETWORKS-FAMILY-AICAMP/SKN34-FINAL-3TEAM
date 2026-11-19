"""#825 공유 답변 공개 계약 CommunityAnswer: 입력 방식별 content 모양(learning AnswerContent.only)과 세 공개 스키마 연결."""
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CORE = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
LEARNING = yaml.safe_load((ROOT / 'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))
SCHEMAS = CORE['components']['schemas']

# learning이 저장하는 입력 방식별 content(비어 있는 칸은 저장하지 않음)와 같은 합성 값
VALID = [
    {'inputType': 'NARRATIVE', 'text': '내 생각', 'content': {'text': '내 생각'}},
    {'inputType': 'SOLUTION_STEPS', 'text': '식: 3+4\n최종 답: 7 개', 'content': {'finalAnswer': '7', 'steps': ['3+4', '']}},
    {'inputType': 'ESSAY', 'text': '주장: 가', 'content': {'essay': {'claim': '가', 'reasons': ['나', '다'], 'rebuttal': '라'}}},
    {'inputType': 'CHOICE', 'text': '사과', 'content': {'choiceIds': ['c1']}},
    {'inputType': 'ORDERING', 'text': '나 → 가', 'content': {'choiceIds': ['c2', 'c1']}},
    {'inputType': 'CLASSIFICATION', 'text': '사과: 과일', 'content': {'assignments': [{'choiceId': 'c1', 'categoryId': 'g1'}]}},
]
INVALID = [
    None, '내 생각', {'text': '답', 'content': {'text': '답'}},
    {'inputType': 'DRAWING', 'text': '답', 'content': {'text': '답'}},
    {'inputType': 'NARRATIVE', 'content': {'text': '답'}},
    {'inputType': 'NARRATIVE', 'text': None, 'content': {'text': '답'}},
    {'inputType': 'NARRATIVE', 'text': '답', 'content': {'text': '답'}, 'memo': '메모'},
    {'inputType': 'NARRATIVE', 'text': '답', 'content': {}},
    {'inputType': 'NARRATIVE', 'text': '답', 'content': {'text': '답', 'choiceIds': ['c1']}},
    {'inputType': 'CHOICE', 'text': '답', 'content': {'text': '답'}},
    {'inputType': 'ORDERING', 'text': '답', 'content': {'choiceIds': ['c1', 2]}},
    {'inputType': 'SOLUTION_STEPS', 'text': '답', 'content': {'finalAnswer': '7'}},
    {'inputType': 'ESSAY', 'text': '답', 'content': {'essay': {'claim': '가', 'reasons': ['나'], 'rebuttal': '라'}}},
    {'inputType': 'ESSAY', 'text': '답', 'content': {'essay': {'claim': '가', 'reasons': ['나', '다']}}},
    {'inputType': 'CLASSIFICATION', 'text': '답', 'content': {'assignments': [{'choiceId': 'c1'}]}},
]


class CommunityAnswerContractTest(unittest.TestCase):
    def validator(self):
        return Draft202012Validator({**SCHEMAS['CommunityAnswer'], 'components': CORE['components']})

    def test_every_input_type_has_exactly_one_content_shape(self):
        validator = self.validator()
        for answer in VALID:
            self.assertEqual([], [e.message for e in validator.iter_errors(answer)], answer['inputType'])
        for answer in INVALID:
            self.assertFalse(validator.is_valid(answer), answer)

    def test_input_types_match_learning(self):
        # core 공개 입력 방식 목록은 learning 공유 답변(CommunitySharedAnswer)과 같아야 한다.
        learning = LEARNING['components']['schemas']['CommunitySharedAnswer']['properties']['inputType']['enum']
        self.assertEqual(sorted(learning), sorted(SCHEMAS['CommunityAnswer']['properties']['inputType']['enum']))
        self.assertEqual(sorted(learning), sorted({a['inputType'] for a in VALID}))

    def test_public_post_schemas_use_community_answer(self):
        ref = {'$ref': '#/components/schemas/CommunityAnswer'}
        for name in ('CommunityPost', 'CommunityOwnPost', 'CommunityLinkedPost'):
            self.assertEqual(ref, SCHEMAS[name]['properties']['answer'], name)


if __name__ == '__main__':
    unittest.main()
