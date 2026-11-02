"""#46 public implementation and explicit unimplemented supplier boundary."""
import re
import unittest
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[2]
class SupportContractTest(unittest.TestCase):
 def test_public_paths_and_auth(self):
  spec=yaml.safe_load((ROOT/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
  source=(ROOT/'backend/core-service/src/main/kotlin/com/sagomungchi/core/support/controller/SupportController.kt').read_text(encoding='utf-8')
  actual={(m.lower(),p.removeprefix('/api/v1')) for m,p in re.findall(r'@(Get|Post|Patch|Delete)Mapping\("([^\"]+)"\)',source)}
  documented={(m,p) for p,ops in spec['paths'].items() for m,op in ops.items() if isinstance(op,dict) and 'Support' in op.get('tags',[])}
  self.assertEqual(actual,documented)
  for p in ('/help','/notices'):
   self.assertNotEqual(spec['paths'][p]['get'].get('security'),[])
  for p in ('/error-reports','/admin/error-reports/{reportId}/corrections'):
   self.assertTrue(any(v['name']=='Idempotency-Key' and v['required'] for v in spec['paths'][p]['post']['parameters']))
 def test_supplier_contract_separated_from_implemented_learning(self):
  actual=yaml.safe_load((ROOT/'contracts/openapi/learning-service.yaml').read_text(encoding='utf-8'))
  required=yaml.safe_load((ROOT/'contracts/openapi/support-learning-required.yaml').read_text(encoding='utf-8'))
  self.assertEqual(len(required['paths']),3)
  # #146 learning 구현: 조회 두 경로는 learning 계약에 있고, core 소비 계약(required)은 그대로 3개
  for path in ('/support/targets/{targetType}/{targetId}','/support/attempts/{attemptId}'):
   self.assertIn(path,actual['paths'])

 def test_correction_security_and_replay_contract(self):
  api=yaml.safe_load((ROOT/'contracts/openapi/support-learning-required.yaml').read_text(encoding='utf-8'))
  self.assertEqual(api['security'],[{'InternalToken':[]}])
  self.assertEqual(api['components']['securitySchemes']['InternalToken']['name'],'X-Internal-Token')
  op=api['paths']['/judgments/{judgmentId}/corrections']['post']
  params={p['name']:p for p in op['parameters']}
  for name in ('X-User-Role','X-Student-Scope','X-User-Id','Idempotency-Key'):
   self.assertTrue(params[name]['required'],name)
  self.assertEqual(params['X-User-Role']['schema']['const'],'ADMIN')
  for name in ('X-Student-Scope','X-User-Id','Idempotency-Key'):
   self.assertEqual(params[name]['schema']['format'],'uuid')
  rules=op['x-correction-rules']
  self.assertEqual(rules['requiredProcessStatus'],'DONE')
  self.assertEqual(rules['notDoneStatus'],409)
  self.assertEqual(rules['sameReportDifferentKeyStatus'],409)
  self.assertEqual(rules['sameKeyDifferentBodyStatus'],422)
  self.assertEqual(rules['sameKeySameBodyReplay'],'entire-first-response')
  self.assertEqual(rules['coreIdempotencyKey'],'persisted-correction-uuid')
  for rule in ('preserveOriginalJudgment','preserveOriginalAnswer','queryLatestCorrection','preserveFollowup','preserveNextActions','allUnknownImpactAllowsSuccess'):
   self.assertTrue(rules[rule],rule)
  self.assertTrue({'400','401','403','404','409','422'}.issubset(op['responses']))
 def test_unknown_and_not_applied_are_valid_successful_impact_states(self):
  from jsonschema import Draft202012Validator, ValidationError
  api=yaml.safe_load((ROOT/'contracts/openapi/support-learning-required.yaml').read_text(encoding='utf-8'))
  impact=api['components']['schemas']['CorrectionResult']['properties']['impact']
  validator=Draft202012Validator(impact)
  validator.validate(dict(conversation='UNKNOWN',aggregation='UNKNOWN',report='UNKNOWN'))
  validator.validate(dict(conversation='UNKNOWN',aggregation='NOT_APPLIED',report='UNKNOWN'))
  with self.assertRaises(ValidationError):
   validator.validate(dict(conversation='UNKNOWN',aggregation='FAILED',report='UNKNOWN'))
  self.assertTrue(impact['x-all-unknown-allows-success'])
  aggregation=impact['properties']['aggregation']
  self.assertIn('학습 수치 집계',aggregation['description'])
  self.assertIn('개별 기록 상세',aggregation['description'])
  self.assertIn('오류나 후속 처리 필요를 뜻하지 않음',aggregation['x-enum-descriptions']['NOT_APPLIED'])
 def test_queries_are_outside_issue_80_and_public_business_statuses_are_documented(self):
  api=yaml.safe_load((ROOT/'contracts/openapi/support-learning-required.yaml').read_text(encoding='utf-8'))
  for path in ('/support/targets/{targetType}/{targetId}','/support/attempts/{attemptId}'):
   self.assertIn('#80 범위 밖',api['paths'][path]['get']['x-tracking-scope'])
  self.assertEqual(api['paths']['/judgments/{judgmentId}/corrections']['post']['x-tracking-scope'],'#80')
  public=yaml.safe_load((ROOT/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
  responses=public['paths']['/admin/error-reports/{reportId}/corrections']['post']['responses']
  self.assertIn('SUPPORT_CORRECTION_CONFLICT',responses['409']['description'])
  self.assertIn('SUPPORT_CORRECTION_REJECTED',responses['422']['description'])

 def test_issue_163_get_errors_are_explicit_on_every_affected_public_operation(self):
  public=yaml.safe_load((ROOT/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
  operations={'/error-reports':'post','/inquiries':'post','/admin/error-reports/{reportId}':'get',
              '/admin/inquiries/{inquiryId}':'get','/admin/error-reports/{reportId}/corrections':'post'}
  for path,method in operations.items():
   responses=public['paths'][path][method]['responses']
   for status,code in [('403','FORBIDDEN'),('404','NOT_FOUND'),('502','SUPPORT_INVALID_RESPONSE'),
                       ('503','SUPPORT_DEPENDENCY_UNAVAILABLE'),('504','LEARNING_TIMEOUT')]:
    self.assertIn(code,responses[status]['description'],(path,status))
    self.assertEqual(responses[status]['content']['application/problem+json']['schema'],{'$ref':'#/components/schemas/Problem'})
   self.assertIn('사전 대상 GET',responses['404']['description'])
   self.assertIn('실제 learning 정정 POST의 403/404도 기존 503',responses['503']['description'])
  consumer=yaml.safe_load((ROOT/'contracts/openapi/support-learning-required.yaml').read_text(encoding='utf-8'))
  for path in ('/support/targets/{targetType}/{targetId}','/support/attempts/{attemptId}'):
   for status,code in [('403','FORBIDDEN'),('404','NOT_FOUND')]:
    description=consumer['paths'][path]['get']['responses'][status]['description']
    self.assertIn(code,description);self.assertIn('application/problem+json',description)
    self.assertIn('503 SUPPORT_DEPENDENCY_UNAVAILABLE',description)
