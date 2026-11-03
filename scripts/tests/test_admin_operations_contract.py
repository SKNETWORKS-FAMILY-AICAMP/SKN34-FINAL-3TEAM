import json
from copy import deepcopy
import hashlib
import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[2]
class AdminOperationsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=yaml.safe_load((ROOT/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
    def test_existing_contracts_preserved(self):
        # The CI checkout is shallow. Keep the reviewed base contract fingerprints
        # in the test sources instead of requiring history or network access.
        baseline=json.loads((Path(__file__).parent/'fixtures/admin_operations_base_contracts.json').read_text(encoding='utf-8'))
        self.assertEqual(baseline['sourceCommit'],'85bf1079c34a3e713bcf5eedf0cfdfd7822dc5a4')
        self.assertEqual(baseline['upstreamSourceCommit'],'c44ace8305d7f14b41e48cb24897279aa6cde46a')
        self.assertEqual(len(baseline['paths']),91)
        self.assertEqual(len(baseline['schemas']),114)
        for section,current in [('paths',self.doc['paths']),('schemas',self.doc['components']['schemas'])]:
            for name,expected in baseline[section].items():
                self.assertIn(name,current)
                reviewed=deepcopy(current[name])
                # #163 explicitly approves only these support operation error responses.
                # Normalize the approved additions while preserving every original field.
                support_operations={'/error-reports':'post','/inquiries':'post',
                    '/admin/error-reports/{reportId}':'get','/admin/inquiries/{inquiryId}':'get',
                    '/admin/error-reports/{reportId}/corrections':'post'}
                if section=='paths' and name in support_operations:
                    responses=reviewed[support_operations[name]]['responses']
                    for status in ('404','502','503','504'):
                        responses.pop(status,None)
                    responses['403']={'$ref':'#/components/responses/LearningProblem'}
                # #242 adds only the GET list operation; the original POST stays fingerprinted.
                if section=='paths' and name=='/admin/notices':
                    reviewed.pop('get',None)
                # FN-ACC-05 guardian password (2026-11-03): guardian entry locks the parent session instead of
                # consuming its refresh cookie, and reauth gains GUARDIAN_PASSWORD. Restore only those approved fields.
                if section=='paths' and name=='/auth/student-sessions':
                    post=reviewed['post']
                    post['description']=('부모 Bearer와 같은 세션의 refresh로 연결·활성 자녀 및 현재 필수/법정대리인 동의를 확인한다. '
                        '학생 access만 발급하고 부모 refresh를 소비·삭제하며 기존 부모 access를 거부한다. PIN 단독 진입은 #58 소유다.')
                    post['security']=[{'BearerAuth':[],'RefreshCookie':[]}]
                    ok=post['responses']['200']
                    ok['description']='학생 access 전용 응답. refresh 쿠키는 만료되며 원문 refresh를 응답하지 않는다.'
                    ok['headers']['Set-Cookie']={'description':'HttpOnly 쿠키. 성공 콜백은 OAuth 상태 쿠키 삭제와 refresh 설정의 복수 Set-Cookie를 반환한다. '
                        '학생 전환·로그아웃은 refresh 쿠키를 만료시킨다.','schema':{'type':'string'}}
                if section=='paths' and name=='/me/reauth':
                    for option in reviewed['post']['requestBody']['content']['application/json']['schema']['oneOf']:
                        purpose=option['properties'].get('purpose')
                        if purpose: purpose['enum'].remove('GUARDIAN_PASSWORD')
                canonical=json.dumps(reviewed,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
                self.assertEqual(expected,hashlib.sha256(canonical).hexdigest(),f'{section}/{name}')
    def test_admin_paths_and_retry_key(self):
        paths=self.doc['paths']
        for name in ['overview','jobs','queues','audit-logs','missions']: self.assertIn('/admin/'+name,paths)
        retry=paths['/admin/jobs/{jobId}/retry']['post']
        self.assertTrue(any(p['name']=='Idempotency-Key' and p['required'] for p in retry['parameters']))
        self.assertEqual(10,sum(len(v) for k,v in paths.items() if k.startswith('/admin/missions')))
    def test_schema_does_not_invent_updated_at_or_expose_free_text(self):
        schemas=self.doc['components']['schemas']
        self.assertNotIn('updatedAt',schemas['OperationJob']['properties'])
        self.assertNotIn('errorDetail',schemas['OperationExecution']['properties'])
        self.assertNotIn('detail',schemas['OperationAudit']['properties'])
        for name,schema in schemas.items():
            if name.startswith('Operation'): Draft202012Validator.check_schema(schema)
    def test_queue_allowlist(self):
        definition=json.loads((ROOT/'infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json').read_text())
        self.assertEqual(30,len(definition['queues']))
        self.assertEqual({'/'},{q['vhost'] for q in definition['queues']})
