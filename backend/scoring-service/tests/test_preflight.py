import base64
import hashlib
import io
import json
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.clients.model_artifacts import S3ModelArtifacts
from app.config import Settings
from app.preflight import FILES, SMALL, PreflightRequest, PreflightService
from tests.test_m2 import model


def fixture():
    loaded = model()
    contents = {f: b"synthetic" for f in FILES}
    contents.update(
        {
            "config.json": json.dumps(
                {"id2label": {str(i): str(i) for i in range(9)}, "problem_type": "regression"}
            ).encode(),
            "train_info.json": json.dumps(loaded.training_config).encode(),
            "score_cuts.json": json.dumps(loaded.score_cuts).encode(),
        }
    )
    request = PreflightRequest(
        name="m2-klue-narrative",
        version="3.0",
        artifactUri="s3://models/models/m2-klue-narrative/3.0/",
        files=[
            {"file": f, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
            for f, b in sorted(contents.items())
        ],
    )
    return contents, request


class Storage:
    def __init__(self, contents):
        self.contents = contents
        self.reads = []
        self.heads = []
        self.override = {}

    def head_object(self, Bucket, Key, ChecksumMode):
        self.heads.append(Key)
        file = Key.rsplit("/", 1)[-1]
        if file not in self.contents:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        raw = self.contents[file]
        return {
            "ContentLength": len(raw),
            "ETag": '"etag"',
            "ChecksumType": "FULL_OBJECT",
            "ChecksumSHA256": base64.b64encode(hashlib.sha256(raw).digest()).decode(),
            **self.override,
        }

    def get_object(self, Bucket, Key, **kwargs):
        file = Key.rsplit("/", 1)[-1]
        self.reads.append(file)
        assert file in SMALL
        assert kwargs == {"IfMatch": '"etag"'}
        return {"Body": io.BytesIO(self.contents[file])}

    def close(self):
        pass


def service(contents):
    storage = Storage(contents)
    artifacts = S3ModelArtifacts(Settings(internal_token="test-token", s3_bucket="models"))
    artifacts._client = Mock(return_value=storage)
    return PreflightService(artifacts), storage


def test_normal_reads_only_three_small_json_and_never_loads_weights():
    contents, request = fixture()
    checker, storage = service(contents)
    result = checker.check(request)
    assert result.status == "PASS"
    assert len(result.files) == 6
    assert set(storage.reads) == SMALL
    checker.artifacts._client.assert_called_once_with(connect_timeout=1, read_timeout=1)


@pytest.mark.parametrize(
    "fault,code",
    [
        ("hash", "HASH_MISMATCH"),
        ("missing", "FILE_MISSING"),
        ("size", "SIZE_MISMATCH"),
        ("composite", "CHECKSUM_UNAVAILABLE"),
        ("no_checksum", "CHECKSUM_UNAVAILABLE"),
    ],
)
def test_storage_failures_are_not_success(fault, code):
    contents, request = fixture()
    checker, storage = service(contents)
    weight = next(f for f in request.files if f.file == "model.safetensors")
    if fault == "hash":
        weight.sha256 = "0" * 64
    if fault == "missing":
        del contents["model.safetensors"]
    if fault == "size":
        weight.bytes += 1
    if fault == "composite":
        storage.override["ChecksumType"] = "COMPOSITE"
    if fault == "no_checksum":
        storage.override["ChecksumSHA256"] = ""
    result = checker.check(request)
    assert result.status == "FAIL"
    assert next(f for f in result.files if f.file == "model.safetensors").code == code
    assert "model.safetensors" not in storage.reads


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com/",
        "s3://other/models/x/",
        "s3://models/private/",
        "s3://models/models/../private/",
        "s3://models/models/%2e%2e/x/",
    ],
)
def test_uri_is_restricted_before_storage_access(uri):
    contents, request = fixture()
    checker, storage = service(contents)
    request.artifact_uri = uri
    assert checker.check(request).code == "INVALID_ARTIFACT_URI"
    assert storage.heads == []


def test_output_shape_and_metadata_are_checked():
    contents, request = fixture()
    contents["config.json"] = b'{"num_labels": 2, "problem_type": "regression"}'
    entry = next(f for f in request.files if f.file == "config.json")
    entry.bytes = len(contents[entry.file])
    entry.sha256 = hashlib.sha256(contents[entry.file]).hexdigest()
    checker, _ = service(contents)
    assert checker.check(request).code == "OUTPUT_MISMATCH"
    contents["train_info.json"] = b"{}"
    entry = next(f for f in request.files if f.file == "train_info.json")
    entry.bytes = 2
    entry.sha256 = hashlib.sha256(b"{}").hexdigest()
    assert checker.check(request).code == "INVALID_METADATA"


def test_internal_auth_strict_request_and_safe_errors():
    contents, request = fixture()
    checker, _ = service(contents)
    app = create_app()
    app.state.preflight_service = checker
    client = TestClient(app)
    body = request.model_dump(by_alias=True)
    assert client.post("/internal/models/preflight", json=body).status_code == 401
    headers = {"X-Internal-Token": "test-token"}
    assert (
        client.post("/internal/models/preflight", json=body, headers=headers).json()["status"]
        == "PASS"
    )
    for modified in [
        dict(body, approved=True),
        dict(body, files=body["files"][:5]),
        dict(body, files=body["files"][:5] + body["files"][:1]),
    ]:
        response = client.post("/internal/models/preflight", json=modified, headers=headers)
        assert response.status_code == 400
        assert response.headers["content-type"].startswith("application/problem+json")


def test_conflicting_config_output_counts_fail_even_with_correct_num_labels():
    contents, request = fixture()
    contents["config.json"] = b'{"num_labels":9,"id2label":{"0":"x"},"problem_type":"regression"}'
    entry = next(f for f in request.files if f.file == "config.json")
    entry.bytes = len(contents[entry.file])
    entry.sha256 = hashlib.sha256(contents[entry.file]).hexdigest()
    checker, _ = service(contents)
    assert checker.check(request).code == "OUTPUT_MISMATCH"
