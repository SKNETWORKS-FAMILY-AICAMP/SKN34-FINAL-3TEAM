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
        callback = api["paths"]["/auth/google/reauth/callback"]["get"]["responses"]
        self.assertEqual({code: list(r["content"]) for code, r in callback.items()}, {"200": ["text/html"], "403": ["text/html"]})
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
            operations += [(method.lower(),path.removeprefix("/api/v1")) for method,path in re.findall(r'@(Get|Post|Put|Patch|Delete)Mapping\("([^\"]+)"\)',(source/name).read_text(encoding="utf-8"))]
        self.assertEqual(len(operations),15)  # #415 POST /me/reauth/password
        for method,path in operations:
            self.assertIn(method,api["paths"][path],path)

    def test_issue_423_core_responses_document_actual_dto_fields(self):
        # Kotlin DTO·Map 응답 모양 그대로(#423). 필드가 늘거나 빠지면 계약 검증이 실패해야 한다.
        api=yaml.safe_load((ROOT/"contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        def schema(path,method,status):
            return api["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"]
        def validator(ref):
            return Draft202012Validator({"components":api["components"],**ref},format_checker=FormatChecker())
        uid="00000000-0000-4000-8000-000000000001"
        cases={
            ("/me","patch","200"):{"userId":uid,"name":"보호자"},
            ("/children/{childId}","patch","200"):{"id":uid,"nickname":"뭉치","grade":4,"birthYear":2016},
            ("/children/{childId}/deletion-impact","get","200"):{"childId":uid,"actions":[{"scope":s,"effect":"안내"} for s in ("UNLINK","PROFILE","RECORDS")],"retainedTransactionsYears":5,"deviceCleanupPending":False},
            ("/me/withdrawal/precheck","get","200"):{"canWithdraw":False,"activeSubscriptions":0,"unresolvedRefunds":0,"retainedTransactionsYears":5,"pendingPayments":1},
            ("/me/withdrawal","post","202"):{"withdrawalRequestId":uid,"status":"REQUESTED","statusToken":"receipt"},
            ("/me/withdrawal","get","200"):{"withdrawalRequestId":uid,"status":"COMPLETED"},
            ("/reports/{reportId}/evidence/{itemId}","get","200"):{"items":[
                {"attemptId":uid,"answerId":uid,"answerVersion":1,"available":True,"quote":"원문","missionTitle":"미션","submittedAt":"2026-11-09T00:00:00Z"},
                {"attemptId":uid,"answerId":uid,"answerVersion":1,"available":False}]},
        }
        for key,valid in cases.items():
            check=validator(schema(*key))
            check.validate(valid)
            self.assertTrue(list(check.iter_errors({**valid,"unexpected":True})),key)
            self.assertTrue(list(check.iter_errors({k:v for k,v in list(valid.items())[1:]})),key)
        precheck=api["components"]["schemas"]["WithdrawalPrecheck"]
        self.assertIn("pendingPayments",precheck["required"])
        profile=api["paths"]["/internal/students/{studentId}/profile"]["get"]["responses"]["200"]
        self.assertIn("parentSharingEnabled",profile["description"])

    def test_core_success_json_responses_are_not_bare_objects(self):
        api=yaml.safe_load((ROOT/"contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        bare=[(method,path,status) for path,ops in api["paths"].items() for method,op in ops.items()
              if isinstance(op,dict) for status,response in op.get("responses",{}).items()
              if status.startswith("2") and (response.get("content") or {}).get("application/json",{}).get("schema")=={"type":"object"}]
        self.assertEqual(bare,[])
