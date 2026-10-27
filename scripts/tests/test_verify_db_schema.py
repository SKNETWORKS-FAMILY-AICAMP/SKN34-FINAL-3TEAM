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
    allowed_values,
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

    def test_confirmed_policy_contract_is_included(self):
        contract = erd_contract()
        core = contract["core_db"]
        learning = contract["learning_db"]
        self.assertEqual(core["guardianship"]["method"]["values"], {"REGISTER"})
        self.assertEqual(core["notification_setting"]["channel"]["values"], {"IN_APP"})
        self.assertIsNone(core["product"]["code"]["values"])
        self.assertFalse(core["student"]["birth_year"]["nullable"])
        self.assertFalse(core["product"]["limits"]["nullable"])
        self.assertNotIn("user_account_id", core["student"])
        self.assertNotIn("speech_transcribed", learning["answer"])
        self.assertEqual(learning["followup"]["source"]["values"], {"LLM", "LLM_RETRY", "BANK"})
        self.assertTrue(learning["followup"]["bank_question_id"]["fk"])
        self.assertEqual(
            learning["followup_bank_question"]["type"]["values"],
            {"ONE_STEP_MORE", "TELL_MORE", "LOOK_AGAIN"},
        )

    def test_explicit_check_annotations_support_one_or_many_values(self):
        for comment, values in [
            ("CHECK[REGISTER] (P02: LINK 미지원)", {"REGISTER"}),
            ("NULL 허용 · CHECK[IN_APP|EMAIL]", {"IN_APP", "EMAIL"}),
            ("CHECK[ai]", {"ai"}),
            ("NULL 허용 · LLM|BANK", {"LLM", "BANK"}),
        ]:
            with self.subTest(comment=comment):
                self.assertEqual(allowed_values(comment), values)

    def test_plain_text_is_not_an_enum_contract(self):
        for comment in [None, "", "core 논리 참조", "FREE, PREMIUM 등; 고정 enum 아님"]:
            with self.subTest(comment=comment):
                self.assertIsNone(allowed_values(comment))

    def test_malformed_explicit_check_cannot_silently_skip_validation(self):
        for comment in [
            "CHECK[]",
            "CHECK[REGISTER",
            "CHECK[REGISTER|]",
            "CHECK[REGISTER,LINK]",
            "CHECK[REGISTER | LINK]",
            "CHECK[REGISTER] CHECK[LINK]",
        ]:
            with self.subTest(comment=comment), self.assertRaises(ValidationError):
                allowed_values(comment)

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

    def test_single_value_accepts_postgres_equality_or_array_display(self):
        tables = {"sample": {"status": {"values": {"ACTIVE"}}}}
        for expression in [
            "((status)::text = 'ACTIVE'::text)",
            "status = ANY (ARRAY['ACTIVE'::character varying])",
        ]:
            with self.subTest(expression=expression):
                constraint = {**self.constraint, "expression": expression}
                self.assertEqual(check_allowed_values("db", tables, [constraint]), 1)

    def test_single_value_missing_widened_or_bypassed_check_fails(self):
        tables = {"sample": {"status": {"values": {"ACTIVE"}}}}
        for expression in [
            None,
            "status = 'INACTIVE'",
            "status = ANY (ARRAY['ACTIVE', 'INACTIVE'])",
            "status = 'ACTIVE' OR true",
            "status = 'ACTIVE' OR status IS NULL",
            "other_status = 'ACTIVE'",
        ]:
            with self.subTest(expression=expression):
                constraints = (
                    [] if expression is None else [{**self.constraint, "expression": expression}]
                )
                with self.assertRaises(ValidationError):
                    check_allowed_values("db", tables, constraints)

    def test_single_value_not_valid_check_is_rejected(self):
        tables = {"sample": {"status": {"values": {"ACTIVE"}}}}
        constraint = {**self.constraint, "expression": "status = 'ACTIVE'", "validated": False}
        with self.assertRaises(ValidationError):
            check_allowed_values("db", tables, [constraint])

    def test_equality_cannot_replace_a_multi_value_contract(self):
        constraint = {**self.constraint, "expression": "status = 'ACTIVE'"}
        with self.assertRaises(ValidationError):
            check_allowed_values("db", self.tables, [constraint])


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
