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
  self.assertNotIn('/support/targets/{targetType}/{targetId}',actual['paths'])
