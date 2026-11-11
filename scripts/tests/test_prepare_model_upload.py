"""Offline upload preparation must reject changed files before producing a plan."""

import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_model_upload import MAX_SINGLE_PUT_BYTES, prepare

NAMES = (
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "train_info.json",
    "score_cuts.json",
    "model.safetensors",
)


class PrepareModelUploadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "모델 원본"
        self.directory.mkdir()
        self.request = {
            "name": "m2-klue-narrative",
            "version": "3.0",
            "artifactUri": "s3://test-models/models/m2-klue-narrative/3.0/",
            "files": [],
        }
        for index, name in enumerate(NAMES):
            # Include binary bytes and CRLF: hash original bytes, not decoded JSON.
            body = bytes([index, 255, 0]) + name.encode() + b"\r\n"
            (self.directory / name).write_bytes(body)
            self.request["files"].append(
                {
                    "file": name,
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )

    def plan(self, request=None, bucket="test-models"):
        return prepare(request or self.request, self.directory, bucket)

    def test_full_file_digest_is_base64_of_raw_bytes_not_ascii_hex(self):
        plan = self.plan()
        self.assertEqual(plan["operation"], "PutObject")
        self.assertEqual(plan["checksumAlgorithm"], "SHA256")
        self.assertEqual(len(plan["files"]), 6)
        for artifact in plan["files"]:
            body = Path(artifact["path"]).read_bytes()
            self.assertEqual(artifact["bytes"], len(body))
            self.assertEqual(
                base64.b64decode(artifact["checksumSHA256"], validate=True),
                hashlib.sha256(body).digest(),
            )
            self.assertEqual(artifact["sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(
                artifact["key"], "models/m2-klue-narrative/3.0/" + artifact["file"]
            )

    def test_same_size_modified_weight_is_rejected(self):
        weight = self.directory / "model.safetensors"
        weight.write_bytes(b"x" * weight.stat().st_size)
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            self.plan()

    def test_size_mismatch_is_rejected(self):
        (self.directory / "tokenizer.json").write_bytes(b"short")
        with self.assertRaisesRegex(ValueError, "SIZE_MISMATCH"):
            self.plan()

    def test_missing_file_is_rejected(self):
        (self.directory / "score_cuts.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.plan()

    def test_duplicate_missing_extra_and_traversal_names_are_rejected(self):
        for entries in (
            self.request["files"][:-1],
            self.request["files"] + [self.request["files"][0]],
            self.request["files"][:-1] + [self.request["files"][0]],
            self.request["files"][:-1]
            + [dict(self.request["files"][-1], file="../weights")],
        ):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                self.plan(dict(self.request, files=entries))

    def test_destination_must_match_expected_bucket_and_safe_prefix(self):
        for uri in (
            "s3://other-models/models/x/",
            "https://test-models/models/x/",
            "s3://test-models/private/x/",
            "s3://test-models/models/x",
            "s3://test-models/models/../x/",
            "s3://test-models/models/%2e%2e/x/",
            "s3://test-models/models//x/",
            "s3://test-models/models/x/?v=1",
            "s3://test-models/models/x/#v1",
            "s3://test-models/models/x\\y/",
        ):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                self.plan(dict(self.request, artifactUri=uri))

    def test_malformed_manifest_fields_are_rejected(self):
        for replacement in (
            {"bytes": True},
            {"bytes": -1},
            {"bytes": "10"},
            {"sha256": "A" * 64},
            {"sha256": "abc"},
            {"sha256": None},
            {"approved": True},
        ):
            request = copy.deepcopy(self.request)
            request["files"][0].update(replacement)
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                self.plan(request)
        with self.assertRaises(ValueError):
            self.plan(dict(self.request, registration={}))

    def test_oversize_file_never_silently_switches_to_multipart(self):
        request = copy.deepcopy(self.request)
        request["files"][-1]["bytes"] = MAX_SINGLE_PUT_BYTES + 1
        with self.assertRaisesRegex(ValueError, "single-PUT"):
            self.plan(request)

    def test_small_json_preflight_limit_is_checked_locally(self):
        request = copy.deepcopy(self.request)
        request["files"][0]["bytes"] = 1024 * 1024 + 1
        with self.assertRaisesRegex(ValueError, "JSON size limit"):
            self.plan(request)

    def run_cli(self, request_path, output_path):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/prepare_model_upload.py"),
                "--request",
                str(request_path),
                "--model-dir",
                str(self.directory),
                "--expected-bucket",
                "test-models",
                "--output",
                str(output_path),
            ],
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
            text=True,
            encoding="utf-8",
        )

    def test_cli_writes_plan_only_after_all_artifacts_match(self):
        request_path = Path(self.temp.name) / "request.json"
        request_path.write_text(json.dumps(self.request), encoding="utf-8-sig")
        output = Path(self.temp.name) / "plan.json"
        (self.directory / "model.safetensors").write_bytes(b"changed")
        result = self.run_cli(request_path, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_cli_never_overwrites_existing_output_or_request(self):
        request_path = Path(self.temp.name) / "request.json"
        original = json.dumps(self.request).encode()
        request_path.write_bytes(original)
        result = self.run_cli(request_path, request_path)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(request_path.read_bytes(), original)
        output = Path(self.temp.name) / "plan.json"
        result = self.run_cli(request_path, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), self.plan())
        result = self.run_cli(request_path, output)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
