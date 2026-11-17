import csv
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "runners" / "explanation_eval.py"
SPEC = importlib.util.spec_from_file_location("explanation_eval", PATH)
ev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ev)


class ExplanationEvalTests(unittest.TestCase):
    def setUp(self):
        self.case = {"id": "test", "grade": 5, "topic": "library", "answer": "I need a library.",
                     "scores": {"overall": 3}, "draft_gt": {
                         "concepts": [{"id": "library", "aliases": ["library", "books"]}],
                         "flag_phrases": ["no reason"]}}

    def test_hidden_gt_does_not_enter_any_generation_stage(self):
        class Fake:
            def generate(self, provider, stage, user):
                if "draft_gt" in user or "SECRET_GT_MARKER" in user:
                    raise AssertionError("GT leaked into prompt")
                return ({"evidence": [{"quote": "library", "observation": "asks for library"}]}
                        if stage == "evidence" else {"text": "Some text"}), stage
        self.case["draft_gt"]["concepts"][0]["aliases"].append("SECRET_GT_MARKER")
        for arm in ev.ARMS:
            ev.output_for(Fake(), self.case, "parent_detail", arm)

    def test_source_quote_validation_rejects_hallucination_and_empty_quote(self):
        for quote in ("a school", "", " "):
            with self.assertRaises(ValueError):
                ev.valid_evidence({"evidence": [{"quote": quote, "observation": "x"}]}, self.case["answer"])
        self.assertEqual(len(ev.valid_evidence({"evidence": [{"quote": "library", "observation": "x"}]}, self.case["answer"])), 1)

    def test_keyword_hit_is_not_a_semantic_correctness_claim(self):
        metrics = ev.proxy_metrics("There is no reason for a library.", self.case, "parent_summary")
        self.assertEqual(metrics["keyword_coverage_proxy"], 1)
        self.assertEqual(metrics["semantic_gt_status"], "UNREVIEWED")
        self.assertEqual(metrics["banned_phrase_flags"], ["no reason"])

    def test_ambiguous_submission_is_not_reposted(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = ev.Client({"EP": "https://api.runpod.ai/v2/test", "KEY": "fake"},
                               Path(tmp), "EP", "KEY", "test", 1, 2)
            message = "test"
            key = ev.digest({"version": ev.VERSION, "identity": client.identity, "provider": "gemma",
                             "stage": "direct", "messages": [{"role": "system", "content": ev.SYSTEM},
                                                               {"role": "user", "content": message}]})
            ev.save(Path(tmp) / "calls" / (key + ".json"), {"state": "STARTED"})
            with self.assertRaisesRegex(ValueError, "UNKNOWN_SUBMISSION"):
                client.generate("gemma", "direct", message)
            self.assertEqual(client.calls, 0)

    def test_failed_calls_are_in_summary_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            ev.save(out / "results.json", {"x": {"state": "FAILED", "arm": "gemma_direct", "error": "BAD_JSON"}})
            summary = ev.summarize(out)
            self.assertEqual(summary["arms"]["gemma_direct"]["attempted"], 1)
            self.assertEqual(summary["arms"]["gemma_direct"]["completed"], 0)
            self.assertEqual(summary["human_review"], "PENDING")

    def test_paid_call_cap_counts_previous_process_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            ev.save(out / "calls" / "previous.json", {"state": "COMPLETED"})
            client = ev.Client({"EP": "https://api.runpod.ai/v2/test", "KEY": "fake"},
                               out, "EP", "KEY", "test", 1, 1)
            with self.assertRaisesRegex(ValueError, "CALL_BUDGET_EXHAUSTED"):
                client.generate("gemma", "new", "new prompt")

    def test_transient_status_error_retries_get_without_resubmitting(self):
        def response(status, data):
            return ev.httpx.Response(status, json=data,
                                     request=ev.httpx.Request("GET", "https://example.invalid"))

        with tempfile.TemporaryDirectory() as tmp, patch.object(ev.httpx, "Client") as factory:
            http = factory.return_value.__enter__.return_value
            http.post.return_value = response(200, {"id": "job-1"})
            http.get.side_effect = [response(500, {}), response(200, {
                "status": "COMPLETED", "output": {"choices": [{"finish_reason": "stop",
                    "message": {"content": '{"text":"recovered"}'}}]}})]
            client = ev.Client({"EP": "https://api.runpod.ai/v2/test", "KEY": "fake"},
                               Path(tmp), "EP", "KEY", "test", 30, 1)
            with patch.object(ev.time, "sleep"):
                value, _ = client.generate("gemma", "direct", "test")
            self.assertEqual(value["text"], "recovered")
            self.assertEqual(http.post.call_count, 1)
            self.assertEqual(http.get.call_count, 2)

    def test_three_rater_exports_hide_model_identity_and_keep_private_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            ev.save(out / "cases.json", [self.case])
            ev.save(out / "results.json", {arm: {"state": "COMPLETED", "case_id": "test",
                    "condition": "parent_detail", "arm": arm, "text": arm + " output"}
                    for arm in ("api_direct", "gemma_direct")})
            args = type("Args", (), {"out": out, "cases": out / "cases.json", "seed": 1})()
            ev.blind(args)
            for i in (1, 2, 3):
                with (out / "review" / f"rater-{i}.csv").open(encoding="utf-8-sig") as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(len(rows), 2)
                self.assertNotIn("arm", rows[0])
                self.assertEqual(rows[0]["accuracy"], "")
            self.assertTrue((out / "BLIND_KEY_DO_NOT_SHARE.json").exists())

    def test_three_different_preferences_remain_no_majority(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            ev.save(out / "BLIND_KEY_DO_NOT_SHARE.json", {"outputs": {
                "O1": {"arm": "api_direct"}, "O2": {"arm": "gemma_two_stage"}},
                "pairs": {"P1": {"A": "O1", "B": "O2"}}})
            paths = []
            for i, vote in enumerate(("A", "B", "TIE")):
                p = out / f"rater{i}.csv"
                ev.write_csv(p, ["pair_id", "preference_A_B_TIE"], [{"pair_id": "P1", "preference_A_B_TIE": vote}])
                paths.append(p)
            args = type("Args", (), {"out": out, "ratings": paths})()
            self.assertEqual(ev.grade(args)["totals"], {"NO_MAJORITY": 1})
            with self.assertRaises(ValueError):
                ev.grade(type("Args", (), {"out": out, "ratings": [paths[0]] * 3})())


if __name__ == "__main__":
    unittest.main()
