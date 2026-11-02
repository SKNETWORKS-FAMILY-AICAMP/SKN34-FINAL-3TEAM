"""Payment controller coverage and permission boundaries in the public contract."""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]

class PaymentContractTest(unittest.TestCase):
    def test_all_payment_routes_are_documented_with_actual_servers(self):
        spec = yaml.safe_load((ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
        source = (ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core/payment/controller/PaymentController.kt").read_text(encoding="utf-8")
        for method, route in re.findall(r'@(Get|Post|Put|Delete)Mapping\("([^"]+)"\)', source):
            path = route.removeprefix("/api/v1").removeprefix("/internal")
            op = spec["paths"][path][method.lower()]
            if route.startswith("/internal"):
                self.assertEqual(op["security"], [{"InternalToken": []}])
                self.assertEqual(op["servers"], [{"url": "/internal"}])
            if path.startswith("/admin/"):
                self.assertIn("PAYMENT_VIEW" if method == "Get" else "PAYMENT_REFUND", op["description"])
            self.assertIn("403", op["responses"])
        webhook = spec["paths"]["/webhooks/tosspayments"]["post"]
        self.assertEqual(webhook["security"], [])
        self.assertEqual(len(webhook["parameters"]), 3)

    def test_product_consumers_do_not_import_payment_repositories(self):
        root = ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core"
        for path in root.rglob("*.kt"):
            if "payment" not in path.relative_to(root).parts:
                self.assertNotIn("core.payment.repository", path.read_text(encoding="utf-8"), str(path))
