"""Keep the #36 public contract aligned with its producer and authentication boundary."""

import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


class AuthOpenApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load(
            (ROOT / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8")
        )

    def test_paths_match_the_six_implemented_controller_operations(self):
        source = (
            ROOT
            / "backend/core-service/src/main/kotlin/com/sagomungchi/core/account/controller/AuthController.kt"
        ).read_text(encoding="utf-8")
        actual = {
            (method.lower(), path.removeprefix("/api/v1"))
            for method, path in re.findall(r'@(Get|Post)Mapping\("([^\"]+)"\)', source)
        }
        documented = {
            (method, path)
            for path, methods in self.spec["paths"].items()
            for method, operation in methods.items()
            if method in {"get", "post"} and {"Auth", "Account"}.intersection(operation.get("tags", []))
        }
        self.assertEqual(len(actual), 6)
        self.assertEqual({item for item in documented if item[1].startswith("/auth/") or item[1] == "/me"}, actual)
        for path in ("/auth/student/devices", "/auth/student/profiles", "/auth/student/login"):
            self.assertNotIn(path, self.spec["paths"])

    def test_consent_and_child_paths_match_implemented_producers(self):
        actual = set()
        for name in ("consent/controller/ConsentController.kt", "guardianship/controller/ChildrenController.kt"):
            source = (ROOT / "backend/core-service/src/main/kotlin/com/sagomungchi/core" / name).read_text(encoding="utf-8")
            actual.update((method.lower(), path.removeprefix("/api/v1")) for method, path in re.findall(r'@(Get|Post)Mapping\("([^\"]+)"\)', source))
        documented = {(method, path) for path, methods in self.spec["paths"].items() for method in methods
                      if path in ("/consent-documents", "/me/consents", "/me/consents/{consentId}/withdrawal", "/children")}
        self.assertEqual(actual, documented)
        self.assertEqual(len(actual), 6)
        schemas = self.spec["components"]["schemas"]
        self.assertNotIn("pinSet", schemas["ChildListItem"]["properties"])
        self.assertEqual(schemas["ChildListItem"]["properties"]["hasRecords"]["type"], ["boolean", "null"])
        self.assertIn("consents", schemas["ChildRegistration"]["required"])

    def test_all_references_resolve_locally(self):
        def visit(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    ref = value["$ref"]
                    self.assertTrue(ref.startswith("#/"), ref)
                    target = self.spec
                    for part in ref[2:].split("/"):
                        target = target[part.replace("~1", "/").replace("~0", "~")]
                    self.assertIsInstance(target, dict)
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)

        visit(self.spec)

    def test_student_contract_has_no_refresh_or_parent_identity(self):
        schemas = self.spec["components"]["schemas"]
        token = schemas["StudentTokenResponse"]
        self.assertEqual(token["properties"]["role"]["const"], "STUDENT")
        self.assertIn("child", token["required"])
        self.assertNotIn("refreshToken", token["properties"])
        me = schemas["StudentMeResponse"]
        self.assertFalse(me["additionalProperties"])
        for private in ("email", "name", "userId", "permissions"):
            self.assertNotIn(private, me["properties"])

    def test_refresh_and_accompanied_entry_have_distinct_security(self):
        paths = self.spec["paths"]
        self.assertEqual(paths["/auth/refresh"]["post"]["security"], [{"RefreshCookie": []}])
        self.assertEqual(
            paths["/auth/student-sessions"]["post"]["security"],
            [{"BearerAuth": [], "RefreshCookie": []}],
        )
        self.assertEqual(
            self.spec["components"]["schemas"]["ParentTokenResponse"]["properties"]["role"]["enum"],
            ["PARENT", "ADMIN"],
        )

    def test_cookie_posts_require_origin_and_requested_with(self):
        for path in ("/auth/refresh", "/auth/logout", "/auth/student-sessions"):
            refs = {value["$ref"] for value in self.spec["paths"][path]["post"]["parameters"]}
            self.assertEqual(
                refs,
                {"#/components/parameters/WebOrigin", "#/components/parameters/RequestedWith"},
            )
        parameters = self.spec["components"]["parameters"]
        self.assertTrue(parameters["WebOrigin"]["required"])
        self.assertEqual(parameters["RequestedWith"]["schema"]["const"], "XMLHttpRequest")

    def test_google_navigation_is_anonymous_and_service_access_is_bearer(self):
        self.assertEqual(self.spec["openapi"], "3.1.0")
        self.assertEqual(self.spec["servers"][0]["url"], "/api/v1")
        self.assertEqual(self.spec["security"], [{"BearerAuth": []}])
        for path in ("/auth/google/authorize", "/auth/google/callback"):
            self.assertEqual(self.spec["paths"][path]["get"]["security"], [])
            self.assertIn("302", self.spec["paths"][path]["get"]["responses"])
        self.assertEqual(
            self.spec["components"]["securitySchemes"]["RefreshCookie"]["name"],
            "sagomungchi_refresh",
        )
