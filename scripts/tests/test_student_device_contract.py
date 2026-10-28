import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
class StudentDeviceContractTest(unittest.TestCase):
    def test_device_contract_security_and_fields(self):
        spec=yaml.safe_load((ROOT/'contracts/openapi/core-service.yaml').read_text(encoding='utf-8'))
        schemas=spec['components']['schemas']; paths=spec['paths']
        self.assertEqual(paths['/auth/student/devices']['post']['security'], [])
        self.assertEqual(paths['/auth/student/login']['post']['security'], [{'StudentDeviceCookie':[]}])
        self.assertEqual(spec['components']['securitySchemes']['StudentDeviceCookie']['name'],'student_device')
        self.assertIn('pinLocked',schemas['StudentDeviceProfile']['required'])
        self.assertNotIn('locked',schemas['StudentDeviceProfile']['properties'])
        self.assertNotIn('refreshToken',schemas['StudentDeviceToken']['properties'])
        self.assertIn('pinLocked',schemas['ChildListItem']['required'])
        self.assertIn('hasRecords',schemas['ChildListItem']['required'])
        params=paths['/children/{childId}/pin']['put']['parameters']
        self.assertTrue(next(p for p in params if p['name']=='X-Reauth-Token')['required'])
