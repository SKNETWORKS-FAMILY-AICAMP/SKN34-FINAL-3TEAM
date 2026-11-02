"""Published REPORT retry acceptance must stay distinct from notification completion."""
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
class AdminReportRetryContractTest(unittest.TestCase):
    def test_accepted_report_contract_does_not_claim_generation_completion(self):
        spec=yaml.safe_load((ROOT/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        responses=spec['paths']['/admin/jobs/{jobId}/retry']['post']['responses']
        self.assertEqual(responses['200']['content']['application/json']['schema'],{'$ref':'#/components/schemas/OperationJob'})
        self.assertEqual(responses['202']['content']['application/json']['schema']['oneOf'],[{'$ref':'#/components/schemas/ReportRetryAccepted'},{'$ref':'#/components/schemas/ConversationRetryAccepted'}])
        self.assertIn('Location',responses['202']['headers'])
        accepted=spec['components']['schemas']['ReportRetryAccepted']
        self.assertEqual(accepted['properties']['status']['const'],'QUEUED')
        self.assertEqual(accepted['properties']['type']['const'],'REPORT')
        self.assertIn('originalJobId',accepted['required'])
        self.assertIn('retryOfJobId',spec['components']['schemas']['OperationJob']['properties'])
        self.assertIn('retryJobId',spec['components']['schemas']['OperationJob']['properties'])
