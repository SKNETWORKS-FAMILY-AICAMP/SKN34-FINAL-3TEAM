"""Read-only observation collection must fail closed on partial results or dataset changes."""

import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from scripts.knowledge import query_examples as collector
from scripts.tests.test_knowledge_contracts import load_fake


class KnowledgeQueryExamplesTest(unittest.TestCase):
    def setUp(self):
        self.api = load_fake().FakeKnowledgeApi()
        self.cases = collector.read_cases(
            Path(__file__).resolve().parents[1] / "knowledge/samples/query-examples.sample.json"
        )
        self.calls = []

    def request(self, url, method, path, token, body=None):
        self.calls.append((url, method, path, body))
        if path == collector.PATH:
            return 200, {"items": [{"version": self.api.version, "status": "ACTIVE"}]}
        if path.startswith("/internal/knowledge/standards?"):
            query = parse_qs(urlsplit(path).query)
            return 200, self.api.standards_sync(query["codes"][0].split(","), grade=int(query["grade"][0]))
        return 200, self.api.thinking_type_sync(path.rsplit("/", 1)[1])

    def collect(self, request=None):
        with patch.object(collector, "request", side_effect=request or self.request):
            return collector.collect("http://learning.test", self.cases, "test-token")

    def test_collects_only_two_code_routes_and_keeps_full_responses(self):
        result = self.collect()
        self.assertTrue(result["collectionComplete"])
        self.assertEqual(len(self.calls), 11)
        self.assertTrue(all(url == "http://learning.test" and method == "GET" and body is None
                            for url, method, _, body in self.calls))
        self.assertEqual(result["qualityAssessment"], "not_evaluated")
        self.assertTrue(all("response" in row and row["latencyMs"] >= 0 for row in result["requests"]))
        self.assertNotIn("embeddingModel", result["dataset"])

    def test_no_active_dataset_stops_before_queries(self):
        result = self.collect(lambda *args: (200, {"items": []}))
        self.assertFalse(result["collectionComplete"])
        self.assertEqual(result["error"], "expected_one_active_dataset")
        self.assertEqual(len(result["requests"]), 1)

    def test_nested_reference_to_other_dataset_is_rejected(self):
        def changed(*args):
            status, response = self.request(*args)
            if "items" in response and response.get("datasetVersion"):
                response["items"][0]["standard"]["ref"]["datasetVersion"] = "kn-20260101-01"
            return status, response

        result = self.collect(changed)
        self.assertFalse(result["collectionComplete"])
        self.assertEqual(result["error"], "dataset_changed_during_collection")

    def test_http_failure_keeps_partial_evidence(self):
        def failed(*args):
            if len(self.calls) >= 2:
                return 500, {"code": "INTERNAL_ERROR"}
            return self.request(*args)

        result = self.collect(failed)
        self.assertFalse(result["collectionComplete"])
        self.assertEqual(result["error"], "unexpected_http_status")
        self.assertEqual(result["requests"][-1]["status"], 500)
        self.assertEqual(result["requests"][1]["status"], 200)

    def test_transport_error_does_not_copy_secret_exception(self):
        def failed(*args):
            raise OSError("test-token must not be recorded")

        result = self.collect(failed)
        self.assertFalse(result["collectionComplete"])
        self.assertEqual(result["error"], "request_failed")
        self.assertNotIn("test-token", str(result))


if __name__ == "__main__":
    unittest.main()
