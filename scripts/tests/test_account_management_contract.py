"""#45 published HTTP, event and schema contracts (no live consumers)."""
import json
from pathlib import Path
import unittest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]

class AccountManagementContractTest(unittest.TestCase):
    def test_student_deleted_payload_rejects_missing_id_unknown_scope_and_student_content(self):
        schema = json.loads((ROOT / "contracts/events/student.deleted.v1.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        valid = {"studentId": "00000000-0000-4000-8000-000000000001", "deletionRequestId": "00000000-0000-4000-8000-000000000002", "scope": "PROFILE"}
        validator.validate(valid)
        validator.validate({**valid, "scope": "RECORDS"})
        for invalid in ({k:v for k,v in valid.items() if k != "deletionRequestId"}, {**valid,"scope":"ALL"}, {**valid,"nickname":"private"}, {**valid,"studentId":"bad"}):
            self.assertTrue(list(validator.iter_errors(invalid)))

    def test_sensitive_http_operations_require_specific_token_and_receipt_cannot_authenticate_elsewhere(self):
        api = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        for path, method in (("/children/{childId}/link", "delete"), ("/children/{childId}/deletion-requests", "post"), ("/me/withdrawal", "post")):
            headers = api["paths"][path][method]["parameters"]
            self.assertTrue(any(p["name"] == "X-Reauth-Token" and p["required"] for p in headers))
        self.assertEqual(api["paths"]["/auth/google/reauth/callback"]["get"]["security"], [])
        self.assertEqual(api["paths"]["/me/withdrawal"]["get"]["security"], [{"BearerAuth": []}, {"WithdrawalReceipt": []}])
        self.assertNotIn("WithdrawalReceipt", api["security"][0])
        completion=api["paths"]["/internal/deletion-requests/{deletionRequestId}/completions"]["post"]
        self.assertEqual(completion["security"], [{"InternalToken": []}])
        self.assertEqual(completion["requestBody"]["content"]["application/json"]["schema"]["properties"]["service"]["enum"], ["learning", "report"])

    def test_every_management_controller_operation_is_published(self):
        import re
        api=yaml.safe_load((ROOT/"contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        source=ROOT/"backend/core-service/src/main/kotlin/com/sagomungchi/core"
        operations=[]
        for name in ("account/controller/AccountManagementController.kt", "account/controller/ReauthenticationController.kt", "guardianship/controller/ChildManagementController.kt"):
            operations += [(method.lower(),path.removeprefix("/api/v1")) for method,path in re.findall(r'@(Get|Post|Patch|Delete)Mapping\("([^\"]+)"\)',(source/name).read_text(encoding="utf-8"))]
        self.assertEqual(len(operations),12)
        for method,path in operations:
            self.assertIn(method,api["paths"][path],path)
