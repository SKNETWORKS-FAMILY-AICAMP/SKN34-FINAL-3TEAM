"""#466 지식 판 관리 스크립트: 샘플 파일을 C1·C4 본문으로 읽고, 내부 토큰·SYSTEM 역할로 관리 경로를 부른다."""

import csv
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "scripts/knowledge/samples"
spec = importlib.util.spec_from_file_location("manage_datasets", ROOT / "scripts/knowledge/manage_datasets.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class FakeLearning(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *args):
        pass

    def _reply(self, status, body):
        data = json.dumps(body).encode("utf-8") if body is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"null")
        FakeLearning.calls.append((self.command, self.path, dict(self.headers), body))
        if self.path.endswith("/activate"):
            self._reply(200, {"status": "ACTIVE"})
            return
        dataset = {"version": "kn-20261111-01", "status": "LOADING", "embeddingModel": "fake-bigram-v1",
                   "chunkCount": len(body["records"]), "chunks": {}, "relationCount": 0, "relations": {}}
        recheck = [{"relationType": "COVERS", "standardCode": "4수01-06", "target": "x", "evidence": "끝이 새 판에 없어 옮기지 않음"}]
        self._reply(201, {"dataset": dataset, "documents": 1, "embeddedTexts": 3, "embeddingRequests": 1,
                          "reusedEmbeddings": 0, "previousVersion": None, "carriedRelations": 0, "recheck": recheck})

    def do_DELETE(self):
        FakeLearning.calls.append((self.command, self.path, dict(self.headers), None))
        self._reply(409, {"code": "KNOWLEDGE_DATASET_STATE_CONFLICT"})


class ManageDatasetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLearning)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeLearning.calls.clear()

    def run_cli(self, *args):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"INTERNAL_TOKEN": "test-token"}), redirect_stdout(out):
            code = manage.main(["--learning-url", self.url, *args])
        return code, json.loads(out.getvalue())

    def test_reads_sample_files_as_contract_rows(self):
        body = manage.load_body(SAMPLES / "curriculum.sample.jsonl", SAMPLES / "relations-review.sample.csv",
                                SAMPLES / "dataset.sample.json")
        self.assertEqual(len(body["records"]), 215)
        self.assertEqual(body["source"]["notice"], "교육부 고시 제2022-33호")
        self.assertEqual(set(body["reviews"][0]), set(manage.REVIEW_COLUMNS))
        self.assertTrue(all(row["reviewer"] == "SAMPLE" for row in body["reviews"] if row["decision"]))

    def test_load_sends_token_and_system_role_then_activates_and_writes_recheck(self):
        with tempfile.TemporaryDirectory() as directory:
            recheck = Path(directory) / "recheck.csv"
            code, printed = self.run_cli("load", "--records", str(SAMPLES / "curriculum.sample.jsonl"),
                                         "--dataset", str(SAMPLES / "dataset.sample.json"),
                                         "--recheck-out", str(recheck), "--activate")
            rows = list(csv.DictReader(recheck.open(encoding="utf-8", newline="")))
        self.assertEqual(code, 0)
        self.assertEqual(printed["body"]["chunkCount"], 215)
        self.assertEqual(printed["body"]["activation"], "ACTIVE")
        self.assertNotIn("test-token", json.dumps(printed))
        method, path, headers, body = FakeLearning.calls[0]
        self.assertEqual((method, path), ("POST", manage.PATH))
        self.assertEqual(headers["X-Internal-Token"], "test-token")
        self.assertEqual(headers["X-User-Role"], "SYSTEM")
        self.assertNotIn("reviews", body)
        self.assertEqual(FakeLearning.calls[1][1], manage.PATH + "/kn-20261111-01/activate")
        self.assertEqual(rows[0]["relationType"], "COVERS")
        self.assertEqual(rows[0]["decision"], "")

    def test_error_status_exits_non_zero(self):
        code, printed = self.run_cli("delete", "kn-20261111-01")
        self.assertEqual(code, 1)
        self.assertEqual(printed["status"], 409)

    def test_token_is_required(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            manage.main(["list"])


if __name__ == "__main__":
    unittest.main()
