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
                # #289 extends reauthentication without removing guardian password support.
                if section=='paths' and name=='/me/reauth':
                    purposes=reviewed['post']['requestBody']['content']['application/json']['schema']['oneOf'][0]['properties']['purpose']['enum']
                    for purpose in ('CHILD_TRANSFER','TRANSFER_ACCEPT'):
                        self.assertIn(purpose,purposes)
                        purposes.remove(purpose)
                # #308 documents existing 409 codes only; request/response schemas stay fingerprinted.
                transfer_guards={'/children/{childId}/link':'delete',
                    '/children/{childId}/deletion-requests':'post','/me/withdrawal':'post'}
                if section=='paths' and name in transfer_guards:
                    conflict=reviewed[transfer_guards[name]]['responses']['409']
                    self.assertIn('TRANSFER_PENDING',conflict['description'])
                    conflict['description']='정책/상태 충돌'
                # #310 corrects the shared refresh cookie sentence to the V24 behavior (student switch keeps the locked
                # parent cookie) and lists PARENT_SESSION_LOCKED on /auth/refresh 401. Restore only those approved fields.
                if section=='paths':
                    for operation in reviewed.values():
                        for response in (operation.get('responses') or {}).values() if isinstance(operation,dict) else ():
                            cookie=(response.get('headers') or {}).get('Set-Cookie') if isinstance(response,dict) else None
                            if cookie and 'description' in cookie:
                                cookie['description']=cookie['description'].replace(
                                    '로그아웃은 refresh 쿠키를 만료시킨다. 학생 전환(/auth/student-sessions)은 잠긴 부모 refresh 쿠키를 지우지 않는다(V24).',
                                    '학생 전환·로그아웃은 refresh 쿠키를 만료시킨다.')
                if section=='paths' and name=='/auth/refresh':
                    self.assertIn('PARENT_SESSION_LOCKED',reviewed['post']['responses']['401']['description'])
                    reviewed['post']['responses']['401']={'$ref':'#/components/responses/Unauthenticated'}
                # #317 documents STUDENT_RECORDS_PRIVATE on the parent record/conversation/report evidence 403s.
                # Remove only that approved suffix or the added 403 entry before default.
                if section=='paths':
                    for operation in reviewed.values():
                        responses=operation.get('responses') if isinstance(operation,dict) else None
                        forbidden=(responses or {}).get('403')
                        if not isinstance(forbidden,dict) or 'description' not in forbidden: continue
                        if forbidden['description'].startswith('권한 없음(FORBIDDEN·CHILD_NOT_LINKED 등) 또는 STUDENT_RECORDS_PRIVATE'):
                            responses.pop('403')
                        else:
                            forbidden['description']=forbidden['description'].replace(' · 학생 비공개 STUDENT_RECORDS_PRIVATE(#206)','')
                # #262 adds only rubric element code·goodThought: core relays learning records unchanged to the dashboard.
                if section=='schemas' and name=='DashboardElement':
                    for field in ('code','goodThought'):
                        reviewed['required'].remove(field)
                        reviewed['properties'].pop(field)
                # #387 adds the attempt start {context} body and the core limit/premium errors; restore only the approved fields.
                if section=='paths' and name=='/missions/{missionId}/attempts':
                    post=reviewed['post']
                    self.assertIn('USAGE_LIMIT_REACHED',post['responses']['429']['description'])
                    self.assertIn('PREMIUM_REQUIRED',post['responses']['403']['description'])
                    post.pop('requestBody')
                    for status in ('400','403','409','429','503'):
                        post['responses'].pop(status)
                    post['description']=('STUDENT 전용. 검증된 본인 학생의 grade·demo를 core DB에서 결정해 /internal/missions/{missionId}/attempts에 쿼리로 전달하며 '
                        '클라이언트 query는 사용하지 않는다. learning은 신규 생성 201·기존 진행 시도 반환 200을 구분하며 core는 상태를 그대로 전달한다. '
                        '신규 시도 제공 범위 검사·기존 진행 시도 선택과 당시 버전 유지는 learning 소유다. 일일 한도는 core Redis 책임이며 learning은 관여하지 않는다. '
                        '후속 한도 연계는 201만 집계하고 200은 집계하지 않는다. 한도 도달 시에도 기존 이어하기는 허용하고 신규 생성만 차단해야 한다. '
                        '한도 검사·기존 시도 판별·신규 생성 차단의 처리 순서는 후속 구현에서 검증한다. Redis 한도 기능은 현재 프록시 구현 범위 밖이다.')
                    post['responses']['200']['description']='기존 진행 시도 반환(이어하기). 후속 일일 한도 집계 대상 아님.'
                    post['responses']['201']['description']='신규 시도 생성. 후속 core Redis 일일 한도 집계 대상.'
                # #355 adds only the ai mission draft usage type; the other call types stay fingerprinted.
                if section=='schemas' and name=='CallType':
                    reviewed['enum'].remove('MISSION_DRAFT')
                # #390 (P24 daily report) adds only the periodType filter/field, daily detail fields and two
                # daily notification types. Remove exactly those additions; every other field stays fingerprinted.
                if section=='paths' and name=='/children/{childId}/reports':
                    get=reviewed['get']
                    self.assertEqual(get['summary'],'연결 자녀의 일일·주간 리포트 목록')
                    get['summary']='연결 자녀의 주간 리포트 목록'
                    get['parameters']=[p for p in get['parameters'] if p.get('name')!='periodType']
                if section=='paths' and name=='/reports/{reportId}/regenerate':
                    self.assertIn('P24',reviewed['post'].pop('description'))
                if section=='schemas' and name in ('ReportSummary','ReportJobAccepted'):
                    reviewed['required'].remove('periodType'); reviewed['properties'].pop('periodType')
                if section=='schemas' and name=='ReportDetail':
                    for field in ('problems','themeSummary'):
                        reviewed['allOf'][1]['properties'].pop(field)
                if section=='schemas' and name=='NotificationType':
                    reviewed.pop('description')
                    for value in ('DAILY_REPORT_COMPLETED','DAILY_REPORT_FAILED'):
                        reviewed['enum'].remove(value)
                if section=='schemas' and name=='NotificationSettings':
                    self.assertEqual(reviewed['properties']['items']['maxItems'],8)
                    reviewed['properties']['items']['maxItems']=6
                # #388 (P20 community) adds only the optional COMMUNITY consent kind, the COMMUNITY_POST report target,
                # the community reviewResult rule and the admin linkedPost. Remove exactly those additions.
                if section=='schemas' and name=='ConsentDocument':
                    kind=reviewed['properties']['kind']
                    self.assertIn('COMMUNITY',kind.pop('description'))
                    kind['enum'].remove('COMMUNITY')
                if section=='schemas' and name=='SupportReportSubmission':
                    target=reviewed['properties']['targetType']
                    self.assertIn('COMMUNITY_POST',target.pop('description'))
                    target['enum'].remove('COMMUNITY_POST')
                if section=='schemas' and name=='SupportReview':
                    self.assertIn('COMMUNITY_POST',reviewed['properties']['reviewResult'].pop('description'))
                if section=='schemas' and name=='SupportReport':
                    self.assertEqual(reviewed['properties'].pop('linkedPost'),{'$ref':'#/components/schemas/CommunityLinkedPost'})
                # #367 adds optional evidence limitations; retain the original evidence fingerprint.
                if section=='schemas' and name=='EvaluationEvidence':
                    self.assertEqual(reviewed['properties'].pop('limitations')['default'],[])
                if section=='schemas' and name=='RegisterModelVersion':
                    self.assertEqual(reviewed.pop('allOf')[0]['then']['required'],['artifactUri'])
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
        self.assertFalse(schemas['OperationAudit']['properties']['detail']['additionalProperties'])
        for name,schema in schemas.items():
            if name.startswith('Operation'): Draft202012Validator.check_schema(schema)
    def test_queue_allowlist(self):
        definition=json.loads((ROOT/'infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json').read_text())
        self.assertEqual(30,len(definition['queues']))
        self.assertEqual({'/'},{q['vhost'] for q in definition['queues']})
