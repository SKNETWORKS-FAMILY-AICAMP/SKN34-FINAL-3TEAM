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
        self.assertNotIn('X-Reauth-Token', [p['name'] for p in params])
        self.assertTrue(paths['/children/{childId}/pin']['put'].get('security', spec['security']))
        renew = paths['/auth/student/renew']['post']
        self.assertEqual(renew['security'], [{'BearerAuth': []}])
        self.assertEqual({p['$ref'].split('/')[-1] for p in renew['parameters']}, {'WebOrigin', 'RequestedWith'})
        success = renew['responses']['200']
        self.assertEqual(success['headers']['Cache-Control']['schema']['const'], 'no-store')
        self.assertEqual(set(success['content']['application/json']['schema']['required']), {'accessToken', 'expiresIn'})
        self.assertTrue({'401', '403', '503'}.issubset(renew['responses']))
