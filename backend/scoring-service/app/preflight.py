"""읽기 전용 모델 사전 검사. 가중치/토크나이저 본문은 다운로드하지 않는다."""

import base64
import hashlib
import json
import time
from contextlib import closing
from typing import Literal
from urllib.parse import unquote

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.clients.model_artifacts import S3ModelArtifacts
from app.config import get_settings
from app.m2.metadata import validate_metadata

FILES = {
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "train_info.json",
    "score_cuts.json",
    "model.safetensors",
}
SMALL = {"config.json", "train_info.json", "score_cuts.json"}
MAX_JSON = 1024 * 1024


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    file: str
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    artifact_uri: str = Field(alias="artifactUri", min_length=1, max_length=2048)
    files: list[Artifact] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_files(self):
        if {f.file for f in self.files} != FILES:
            raise ValueError("manifest must contain the six supported files exactly once")
        return self


class FileCheck(BaseModel):
    file: str
    status: Literal["PASS", "FAIL"]
    code: str


class PreflightResult(BaseModel):
    status: Literal["PASS", "FAIL"]
    code: str
    files: list[FileCheck]


def failed(code, files=None):
    return PreflightResult(status="FAIL", code=code, files=files or [])


class PreflightService:
    def __init__(self, artifacts: S3ModelArtifacts):
        self.artifacts = artifacts

    def check(self, request: PreflightRequest) -> PreflightResult:
        # Bucket is configuration-owned. Never follow a supplied URL or arbitrary key prefix.
        try:
            bucket, prefix = self.artifacts._location(request.artifact_uri)
            if (
                not prefix.startswith("models/")
                or any(part in {"", ".", ".."} for part in unquote(prefix).rstrip("/").split("/"))
                or any(c in prefix for c in ("\\", ":", "%", "<", ">"))
            ):
                return failed("INVALID_ARTIFACT_URI")
        except ValueError:
            return failed("INVALID_ARTIFACT_URI")
        if request.name not in {"m2-klue-narrative", "m2-klue-essay"}:
            return failed("UNSUPPORTED_MODEL")
        deadline = time.monotonic() + 15
        checks, documents = [], {}
        with closing(self.artifacts._client(connect_timeout=1, read_timeout=1)) as client:
            for entry in request.files:
                if time.monotonic() >= deadline:
                    return failed("PREFLIGHT_TIMEOUT", checks)
                try:
                    head = client.head_object(
                        Bucket=bucket, Key=prefix + entry.file, ChecksumMode="ENABLED"
                    )
                    code = "OK"
                    if head["ContentLength"] != entry.bytes:
                        code = "SIZE_MISMATCH"
                    elif entry.file in SMALL:
                        if entry.bytes > MAX_JSON:
                            code = "JSON_TOO_LARGE"
                        else:
                            options = {"IfMatch": head["ETag"]}
                            response = client.get_object(
                                Bucket=bucket, Key=prefix + entry.file, **options
                            )
                            with closing(response["Body"]) as body:
                                raw = body.read(MAX_JSON + 1)
                            if len(raw) != entry.bytes or len(raw) > MAX_JSON:
                                code = "SIZE_MISMATCH"
                            elif hashlib.sha256(raw).hexdigest() != entry.sha256:
                                code = "HASH_MISMATCH"
                            else:
                                documents[entry.file] = json.loads(raw)
                                if not isinstance(documents[entry.file], dict):
                                    code = "INVALID_METADATA"
                    else:
                        checksum = head.get("ChecksumSHA256", "")
                        # ETag, user metadata and multipart COMPOSITE are not file SHA-256.
                        if head.get("ChecksumType") == "COMPOSITE" or not checksum:
                            code = "CHECKSUM_UNAVAILABLE"
                        else:
                            try:
                                digest = base64.b64decode(checksum, validate=True)
                                code = (
                                    "OK"
                                    if len(digest) == 32 and digest.hex() == entry.sha256
                                    else "HASH_MISMATCH"
                                )
                            except ValueError:
                                code = "CHECKSUM_UNAVAILABLE"
                except ClientError as exc:
                    error = str(exc.response.get("Error", {}).get("Code", ""))
                    code = {
                        "404": "FILE_MISSING",
                        "NoSuchKey": "FILE_MISSING",
                        "403": "ACCESS_DENIED",
                        "AccessDenied": "ACCESS_DENIED",
                        "412": "OBJECT_CHANGED",
                        "PreconditionFailed": "OBJECT_CHANGED",
                    }.get(error, "STORAGE_UNAVAILABLE")
                except (BotoCoreError, OSError):
                    code = "STORAGE_UNAVAILABLE"
                except (ValueError, KeyError, TypeError):
                    code = "INVALID_METADATA"
                checks.append(
                    FileCheck(file=entry.file, status="PASS" if code == "OK" else "FAIL", code=code)
                )
        if time.monotonic() >= deadline:
            return failed("PREFLIGHT_TIMEOUT", checks)
        if any(c.status == "FAIL" for c in checks):
            return failed("FILE_CHECK_FAILED", checks)
        try:
            _, width, _, _ = validate_metadata(
                request.name, documents["train_info.json"], documents["score_cuts.json"]
            )
            config = documents["config.json"]
            labels = config.get("id2label")
            explicit_width = config.get("num_labels")
            valid_labels = (
                isinstance(labels, dict) and set(labels) == {str(i) for i in range(width)}
                if labels is not None
                else explicit_width == width
            )
            if (
                not valid_labels
                or explicit_width not in (None, width)
                or config.get("problem_type") != "regression"
            ):
                return failed("OUTPUT_MISMATCH", checks)
        except (ValueError, KeyError, TypeError, OverflowError):
            return failed("INVALID_METADATA", checks)
        return PreflightResult(status="PASS", code="FILES_AND_METADATA_VERIFIED", files=checks)


router = APIRouter(prefix="/internal/models", tags=["models"])


@router.post("/preflight", response_model=PreflightResult)
def preflight(body: PreflightRequest, request: Request) -> PreflightResult:
    service = getattr(request.app.state, "preflight_service", None)
    if service is None:
        service = PreflightService(S3ModelArtifacts(get_settings()))
    return service.check(body)
