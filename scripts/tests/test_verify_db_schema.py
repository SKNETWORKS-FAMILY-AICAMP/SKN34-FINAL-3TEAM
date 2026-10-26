"""Regression tests for omissions that could otherwise make schema CI pass."""

import copy
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_db_schema import (  # noqa: E402
    ROOT,
    ValidationError,
    canonical_expression,
    check_allowed_values,
    check_indexes,
    erd_contract,
    index_contract,
)


class ContractTests(unittest.TestCase):
    def test_empty_erd_cannot_succeed_without_checks(self):
        with self.assertRaises(ValidationError):
            erd_contract("")
        with self.assertRaises(ValidationError):
            index_contract("## 6. 인덱스\n\n## 7. 가정\n")

    def test_shared_and_lowercase_check_values_are_included(self):
        contract = erd_contract()
        self.assertEqual(contract["core_db"]["llm_usage"]["service"]["values"], {"ai", "scoring"})
        self.assertEqual(
            contract["learning_db"]["answer"]["input_type"]["values"],
            contract["learning_db"]["mission_version"]["input_type"]["values"],
        )
        self.assertEqual(
            contract["core_db"]["notification_setting"]["type"]["values"],
            contract["core_db"]["notification"]["type"]["values"],
        )
        self.assertEqual(
            contract["core_db"]["correction"]["target_type"]["values"],
            contract["core_db"]["error_report"]["target_type"]["values"],
        )

    def test_index_table_override_and_partial_predicate(self):
        indexes = index_contract((ROOT / "docs/design/erd.md").read_text(encoding="utf-8"))
        self.assertIn(
            {
                "table": "mission_version",
                "columns": ["thinking_type", "grade_min", "grade_max"],
                "predicate": "",
            },
            indexes["learning_db"],
        )
        self.assertIn(
            {
                "table": "outbox_event",
                "columns": ["created_at"],
                "predicate": "published_at IS NULL",
            },
            indexes["report_db"],
        )

    def test_expression_normalization_preserves_literal_case_and_spaces(self):
        self.assertEqual(canonical_expression("((status)::text = 'A B'::text)"), "status='A B'")
        self.assertNotEqual(
            canonical_expression("status = 'ACTIVE'"), canonical_expression("status = 'active'")
        )

    def test_optimization_does_not_disable_validation(self):
        result = subprocess.run(
            [
                sys.executable,
                "-O",
                "-c",
                'from verify_db_schema import require; require(False, "schema mismatch")',
            ],
            cwd=ROOT / "scripts",
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema mismatch", result.stderr)


class AllowedValuesTests(unittest.TestCase):
    def setUp(self):
        self.tables = {"sample": {"status": {"values": {"ACTIVE", "INACTIVE"}}}}
        self.constraint = {
            "table": "sample",
            "kind": "c",
            "columns": ["status"],
            "validated": True,
            "expression": "((status)::text = ANY ((ARRAY['INACTIVE'::character varying, "
            "'ACTIVE'::character varying])::text[]))",
        }

    def test_postgres_display_casts_and_order_do_not_matter(self):
        self.assertEqual(check_allowed_values("db", self.tables, [self.constraint]), 1)

    def test_missing_changed_or_bypassed_checks_fail(self):
        for expression in [
            None,
            "status = ANY (ARRAY['ACTIVE'])",
            "status = ANY (ARRAY['ACTIVE', 'INACTIVE', 'INVALID'])",
            "status = ANY (ARRAY['ACTIVE', 'INACTIVE']) OR true",
            "other_status = ANY (ARRAY['ACTIVE', 'INACTIVE'])",
        ]:
            with self.subTest(expression=expression):
                constraints = (
                    [] if expression is None else [{**self.constraint, "expression": expression}]
                )
                with self.assertRaises(ValidationError):
                    check_allowed_values("db", self.tables, constraints)

    def test_not_valid_check_is_rejected(self):
        with self.assertRaises(ValidationError):
            check_allowed_values("db", self.tables, [{**self.constraint, "validated": False}])


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.expected = [
            {"table": "sample", "columns": ["owner", "created_at"], "predicate": "status='ACTIVE'"}
        ]
        self.actual = {
            "table": "sample",
            "columns": ["owner", "created_at"],
            "predicate": "((status)::text = 'ACTIVE'::text)",
            "valid": True,
            "ready": True,
            "method": "btree",
        }

    def test_matching_index(self):
        self.assertEqual(check_indexes("db", self.expected, [self.actual]), 1)

    def test_missing_wrong_order_wrong_predicate_and_unusable_index_fail(self):
        for change in [
            None,
            {"columns": ["created_at", "owner"]},
            {"predicate": ""},
            {"predicate": "status='INACTIVE'"},
            {"valid": False},
            {"ready": False},
            {"method": "hash"},
        ]:
            with self.subTest(change=change):
                actual = [] if change is None else [{**copy.deepcopy(self.actual), **change}]
                with self.assertRaises(ValidationError):
                    check_indexes("db", self.expected, actual)


if __name__ == "__main__":
    unittest.main()
