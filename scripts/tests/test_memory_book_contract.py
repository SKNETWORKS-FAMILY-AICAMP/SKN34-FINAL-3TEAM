"""추억 그림책(#966·#975) core 공개 API 계약이 controller·응답 data class·오류 코드·web 호출과 같은지 대조한다.

core 통합 시험(MemoryBookIntegrationTest)이 실제 동작을 확인하고, 이 시험은 OpenAPI 문서가 그 코드에서 벗어나지 않게 막는다.
공용 E2E 스택에서 그림책 시험이 건너뛰지 않는지도 함께 본다.
"""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'backend/core-service/src/main/kotlin/com/sagomungchi/core'
BOOK = CORE / 'memorybook'


def fields(source, name):
    """Kotlin data class 생성자 칸 이름."""
    match = re.search(rf'data class {name}\((.*?)\)\s*(?:\{{|\n)', source, re.S)
    assert match, name
    return {m for m in re.findall(r'val (\w+):', match[1])}


class MemoryBookContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / 'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        cls.schemas = cls.spec['components']['schemas']
        cls.controller = (BOOK / 'controller/MemoryBookController.kt').read_text(encoding='utf-8')
        cls.service = (BOOK / 'service/MemoryBookService.kt').read_text(encoding='utf-8')
        cls.jobs = (BOOK / 'service/MemoryBookJobService.kt').read_text(encoding='utf-8')
        cls.domain = (BOOK / 'domain/MemoryBook.kt').read_text(encoding='utf-8')

    def operations(self):
        return {(method, path) for path, methods in self.spec['paths'].items() for method, op in methods.items()
                if isinstance(op, dict) and 'MemoryBook' in op.get('tags', [])}

    def test_documented_operations_match_controller(self):
        actual = {(m.lower(), p.removeprefix('/api/v1'))
                  for m, p in re.findall(r'@(Get|Post|Put|Patch|Delete)Mapping\("([^"]+)"\)', self.controller)}
        # 회차 목록·발급·발급 목록·받기 주소 + 같이 읽음 표시(#1025)
        self.assertEqual(5, len(actual))
        self.assertEqual(actual, self.operations())

    def test_response_schemas_match_data_classes(self):
        pairs = {
            'MemoryBook': 'MemoryBookView', 'MemoryBookRound': 'MemoryBookRound', 'MemoryBookRoundItem': 'MemoryBookRoundView',
            'MemoryBookRoundPage': 'MemoryBookRoundPage', 'MemoryBookPage': 'MemoryBookPage', 'MemoryBookDownload': 'MemoryBookDownload',
        }
        for schema, kotlin in pairs.items():
            with self.subTest(schema=schema):
                properties = set(self.schemas[schema]['properties'])
                self.assertEqual(fields(self.domain, kotlin), properties)
                # Jackson은 null 칸도 싣는다(NON_NULL 없음): 모든 칸이 required여야 문서와 응답이 같다
                self.assertEqual(properties, set(self.schemas[schema]['required']))
        request = fields(self.controller, 'RoundRequest')
        self.assertEqual(request, set(self.schemas['MemoryBookRound']['properties']))
        self.assertEqual({'rounds'}, fields(self.controller, 'CreateMemoryBookRequest'))

    def test_status_enum_is_stored_states_plus_expired(self):
        stored = set(re.search(r'enum class MemoryBookStatus \{ ([^}]+) \}', self.domain)[1].replace(' ', '').split(','))
        self.assertEqual(stored | {'EXPIRED'}, set(self.schemas['MemoryBook']['properties']['status']['enum']))
        self.assertIn('"EXPIRED"', self.domain)

    def test_every_public_error_code_is_documented(self):
        codes = set(re.findall(r'BusinessException\(HttpStatus\.\w+, "([A-Z_]+)"', self.service + self.jobs))
        self.assertTrue({'MEMORY_BOOK_NOT_FOUND', 'MEMORY_BOOK_EXPIRED', 'USAGE_LIMIT_REACHED', 'THEME_FRAME_NOT_FOUND'} <= codes)
        text = yaml.safe_dump({p: self.spec['paths'][p] for _, p in self.operations()}, allow_unicode=True)
        for code in codes | {'CHILD_NOT_LINKED', 'PREMIUM_REQUIRED', 'REFUND_IN_PROGRESS'}:
            self.assertIn(code, text, code)

    def test_create_returns_202_new_and_200_reused(self):
        operation = self.spec['paths']['/children/{childId}/memory-books']['post']
        self.assertTrue({'200', '202'} <= set(operation['responses']))
        self.assertIn('HttpStatus.ACCEPTED else HttpStatus.OK', self.controller)
        self.assertEqual(1, self.schemas['MemoryBookCreateRequest']['properties']['rounds']['maxItems'])

    def test_web_calls_the_documented_paths(self):
        web = (ROOT / 'frontend/web/src/data/memoryBook/api.ts').read_text(encoding='utf-8')
        for path in ('/memory-books/rounds?', '/memory-books`', '/memory-books?', '/download`'):
            self.assertIn(path, web)

    def test_shared_e2e_stack_runs_the_memory_book_scenario(self):
        spec = (ROOT / 'frontend/web/tests/e2e/memory-book.spec.ts').read_text(encoding='utf-8')
        self.assertNotIn('E2E_MEMORY_BOOK', spec)
        self.assertNotIn('test.skip(', spec)
        compose = yaml.safe_load((ROOT / 'compose.e2e.yaml').read_text(encoding='utf-8'))['services']
        self.assertEqual('sagomungchi-local-missions', compose['learning-service']['environment']['ASSET_S3_BUCKET'])
        worker = compose['report-worker']['environment']
        self.assertTrue(worker['MEMORY_BOOK_ASSET_ORIGINS'])
        self.assertTrue(worker['MEMORY_BOOK_ASSET_INTERNAL_ORIGINS'].endswith('=http://minio:9000'))


if __name__ == '__main__':
    unittest.main()
