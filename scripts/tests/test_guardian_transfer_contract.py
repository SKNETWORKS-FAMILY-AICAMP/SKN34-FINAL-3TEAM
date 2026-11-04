"""#308: 이관 구현의 공개 경로·오류와 재인증 계약 누락 회귀 방지."""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


class GuardianTransferContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        cls.spec = (ROOT / "docs/design/api-spec.md").read_text(encoding="utf-8")

    def test_controller_operations_are_listed_in_account_table_and_openapi(self):
        controller = (ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core/guardianship/controller/GuardianTransferController.kt").read_text(encoding="utf-8")
        operations = re.findall(r'@(Get|Post)Mapping\("(/api/v1/guardian-transfers[^\"]*)"\)', controller)
        self.assertEqual(len(operations), 7)
        table = self.spec.split("### 2.1 ", 1)[1].split("### 2.2 ", 1)[0]
        for method, full_path in operations:
            path = full_path.removeprefix("/api/v1")
            self.assertIn(f"| {method.upper()} | `{path}` |", table)
            operation = self.api["paths"][path][method.lower()]
            self.assertNotIn("로컬 이관 실험", operation["description"])
            self.assertIn("기본 false", operation["description"])

    def test_errors_have_correct_status_at_the_affected_operations(self):
        cases = {
            ("/guardian-transfers/recipient", "404"): ["TRANSFER_RECIPIENT_NOT_FOUND"],
            ("/guardian-transfers", "409"): ["TRANSFER_PENDING", "TRANSFER_CHILD_UNAVAILABLE", "TRANSFER_PAYMENT_BLOCKED"],
            ("/guardian-transfers/{id}/accept", "409"): ["TRANSFER_ALREADY_RESOLVED", "TRANSFER_CHILD_UNAVAILABLE", "TRANSFER_ACTIVITY_IN_PROGRESS", "TRANSFER_PAYMENT_BLOCKED"],
            ("/guardian-transfers/{id}/reject", "409"): ["TRANSFER_ALREADY_RESOLVED"],
            ("/guardian-transfers/{id}/cancel", "409"): ["TRANSFER_ALREADY_RESOLVED"],
            ("/children/{childId}/deletion-requests", "409"): ["TRANSFER_PENDING"],
            ("/me/withdrawal", "409"): ["TRANSFER_PENDING"],
            ("/children/{childId}/link", "409"): ["TRANSFER_PENDING"],
        }
        error_table = self.spec.split("### 1.3 ", 1)[1].split("### 1.4 ", 1)[0]
        for (path, status), codes in cases.items():
            method = "delete" if path.endswith("/link") else "post"
            description = self.api["paths"][path][method]["responses"][status]["description"]
            for code in codes:
                self.assertIn(code, description)
                self.assertIn(f"| `{code}` | {status} |", error_table)

    def test_transfer_state_and_reauth_scopes_are_documented(self):
        self.assertIn("### 5.17 #289", self.spec)
        self.assertNotIn("### #289", self.spec)
        states = self.spec.split("### 1.5 ", 1)[1].split("### 1.6 ", 1)[0]
        for state in ["PENDING", "ACCEPTED", "REJECTED", "CANCELLED"]:
            self.assertIn(f"`{state}`", states)
        reauth = self.spec.split("### 5.6 ", 1)[1].split("### 5.7 ", 1)[0]
        for purpose in ["PIN_CHANGE", "CHILD_UNLINK", "CHILD_DELETE", "WITHDRAWAL", "GUARDIAN_PASSWORD", "CHILD_TRANSFER", "TRANSFER_ACCEPT"]:
            self.assertIn(purpose, reauth)
