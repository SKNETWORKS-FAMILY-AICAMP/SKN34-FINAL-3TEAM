"""Opt-in #493 integration test: disposable localhost MinIO, never AWS.

MODEL_UPLOAD_LOCAL=true pytest tests/test_model_upload_local.py
See docs/report/scoring.md#6-모델-산출물-sha-256-업로드-절차-493 for the fixed local container setup.
"""

import hashlib
import os
import sys
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError

from app.clients.model_artifacts import S3ModelArtifacts
from app.config import Settings
from app.preflight import SMALL, PreflightService
from tests.test_preflight import fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from prepare_model_upload import prepare  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.getenv("MODEL_UPLOAD_LOCAL") != "true", reason="disposable localhost MinIO only"
)


@pytest.mark.parametrize("weight_bytes", [1024, 442_539_656])
def test_single_put_plan_and_existing_preflight(tmp_path, weight_bytes):
    # Fixed endpoint and explicit dummy credentials: no AWS credential discovery.
    client = boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:58193",
        aws_access_key_id="model-upload-local",
        aws_secret_access_key="model-upload-test-only",
        region_name="ap-northeast-2",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 0}),
    )
    bucket = "issue493-" + uuid4().hex
    prefix = "models/m2-klue-narrative/3.0/"
    contents, request = fixture()
    request.artifact_uri = f"s3://{bucket}/{prefix}"
    for name, body in contents.items():
        (tmp_path / name).write_bytes(body)
    weight = tmp_path / "model.safetensors"
    with weight.open("wb") as stream:
        stream.truncate(weight_bytes)
    with weight.open("rb") as stream:
        weight_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    weight_entry = next(item for item in request.files if item.file == weight.name)
    weight_entry.bytes, weight_entry.sha256 = weight_bytes, weight_hash
    plan = prepare(request.model_dump(by_alias=True), tmp_path, bucket)
    client.create_bucket(Bucket=bucket)
    try:
        for artifact in plan["files"]:
            with Path(artifact["path"]).open("rb") as body:
                put = client.put_object(
                    Bucket=bucket,
                    Key=artifact["key"],
                    Body=body,
                    ChecksumAlgorithm="SHA256",
                    ChecksumSHA256=artifact["checksumSHA256"],
                    IfNoneMatch="*",
                )
            assert put["ChecksumSHA256"] == artifact["checksumSHA256"]
            head = client.head_object(Bucket=bucket, Key=artifact["key"], ChecksumMode="ENABLED")
            assert head["ContentLength"] == artifact["bytes"]
            assert head["ChecksumType"] == "FULL_OBJECT"
            assert head["ChecksumSHA256"] == artifact["checksumSHA256"]

        tracked = Mock(wraps=client)
        artifacts = S3ModelArtifacts(Settings(internal_token="local", s3_bucket=bucket))
        artifacts._client = Mock(return_value=tracked)
        checker = PreflightService(artifacts)
        result = checker.check(request)
        assert result.status == "PASS"
        assert result.code == "FILES_AND_METADATA_VERIFIED"
        assert tracked.head_object.call_count == 6
        assert {
            c.kwargs["Key"].rsplit("/", 1)[-1] for c in tracked.get_object.call_args_list
        } == SMALL

        weight_entry.sha256 = "0" * 64
        mismatch = checker.check(request)
        assert (
            next(item for item in mismatch.files if item.file == weight.name).code
            == "HASH_MISMATCH"
        )

        # A malformed SHA-256 must fail at the object store, not become an object.
        with pytest.raises(ClientError) as bad_digest:
            client.put_object(
                Bucket=bucket,
                Key=prefix + "bad-digest",
                Body=b"changed",
                ChecksumAlgorithm="SHA256",
                ChecksumSHA256=plan["files"][0]["checksumSHA256"],
            )
        # MinIO uses a different code from AWS S3 for this integrity failure.
        assert bad_digest.value.response["Error"]["Code"] in {
            "BadDigest",
            "XAmzContentChecksumMismatch",
        }
        assert bad_digest.value.response["ResponseMetadata"]["HTTPStatusCode"] == 400
        with pytest.raises(ClientError) as absent:
            client.head_object(Bucket=bucket, Key=prefix + "bad-digest")
        assert absent.value.response["ResponseMetadata"]["HTTPStatusCode"] == 404

        # Do not silently overwrite an existing key in the new-object procedure.
        with pytest.raises(ClientError) as conflict:
            client.put_object(
                Bucket=bucket, Key=prefix + "config.json", Body=b"changed", IfNoneMatch="*"
            )
        assert conflict.value.response["ResponseMetadata"]["HTTPStatusCode"] == 412

        config_artifact = next(item for item in plan["files"] if item["file"] == "config.json")
        existing = client.head_object(Bucket=bucket, Key=config_artifact["key"])
        with pytest.raises(ClientError) as stale:
            client.put_object(
                Bucket=bucket,
                Key=config_artifact["key"],
                Body=contents["config.json"],
                ChecksumAlgorithm="SHA256",
                ChecksumSHA256=config_artifact["checksumSHA256"],
                IfMatch='"stale-etag"',
            )
        assert stale.value.response["ResponseMetadata"]["HTTPStatusCode"] == 412
        repaired = client.put_object(
            Bucket=bucket,
            Key=config_artifact["key"],
            Body=contents["config.json"],
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=config_artifact["checksumSHA256"],
            IfMatch=existing["ETag"],
        )
        assert repaired["ChecksumSHA256"] == config_artifact["checksumSHA256"]
    finally:
        # Only delete explicitly named test objects from this test's unique bucket.
        for name in [*contents, "bad-digest"]:
            client.delete_object(Bucket=bucket, Key=prefix + name)
        client.delete_bucket(Bucket=bucket)
        client.close()
