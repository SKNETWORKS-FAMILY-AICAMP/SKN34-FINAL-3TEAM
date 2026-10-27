"""Real local MinIO + PostgreSQL; upstream records/AI/message contracts stay synthetic."""

import asyncio
import io
import re
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import boto3
import docker
import httpx
import pytest
from botocore.config import Config
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select

from app.bootstrap import create_app
from app.clients.storage import ObjectStorage, report_key, report_prefix
from app.config import Settings
from app.generation.locking import JobLocks
from app.generation.repository import report_file, weekly_report
from app.generation.service import GenerationService
from app.query.router import query_service
from app.query.service import QueryService
from app.rendering.generator import TYPES, RenderingGenerator
from app.rendering.renderer import ReportRenderer
from tests.render_helpers import fixed_result
from tests.report_helpers import FakeCodec, command_for
from tests.test_rendering import FakeRenderer
from tests.test_report_query import headers

BUCKET = "sagomungchi-local-reports"


@pytest.fixture(scope="module")
def minio_endpoint():
    # Follow the team's pinned image, never an unversioned test-only substitute.
    compose = Path(__file__).resolve().parents[3] / "compose.minio.yaml"
    image = re.search(
        r"image: (cgr\.dev/chainguard/minio@sha256:[a-f0-9]+)", compose.read_text(encoding="utf-8")
    )
    assert image, "Pinned MinIO image missing from compose.minio.yaml"
    image = image.group(1)
    access, secret = f"test-{uuid4().hex}", uuid4().hex
    container = None
    client = docker.from_env()
    try:
        try:
            client.images.get(image)
        except docker.errors.ImageNotFound:
            client.images.pull(image)
        container = client.containers.run(
            image,
            ["--certs-dir", "/tmp/certs", "server", "--address", ":9000", "/data"],
            detach=True,
            environment={"MINIO_ROOT_USER": access, "MINIO_ROOT_PASSWORD": secret},
            ports={"9000/tcp": ("127.0.0.1", None)},
            read_only=True,
            tmpfs={"/data": "rw,uid=65532,gid=65532,size=256m", "/tmp": "rw,size=64m"},
            mem_limit="1g",
            labels={"sagomungchi.test": "report-minio"},
        )
        container.reload()
        port = container.attrs["NetworkSettings"]["Ports"]["9000/tcp"][0]["HostPort"]
        internal, public = f"http://127.0.0.1:{port}", f"http://localhost:{port}"
        with httpx.Client(timeout=1, trust_env=False) as http:
            deadline = time.monotonic() + 30
            while True:
                try:
                    if http.get(f"{internal}/minio/health/ready").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if time.monotonic() > deadline:
                    pytest.fail("Isolated MinIO did not become ready within 30 seconds")
                time.sleep(0.1)
        yield internal, public, access, secret
    finally:
        # Remove only this fixture's container; /data is temporary, with no host volume.
        if container is not None:
            container.remove(force=True, v=True)
        client.close()


@pytest.fixture
def minio_storage(minio_endpoint, monkeypatch):
    internal, public, access, secret = minio_endpoint
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", access)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", secret)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    settings = Settings(s3_endpoint_url=internal, s3_public_endpoint_url=public, s3_bucket=BUCKET)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    storage = ObjectStorage.configured()
    admin = boto3.client(
        "s3",
        endpoint_url=internal,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    if BUCKET not in [bucket["Name"] for bucket in admin.list_buckets()["Buckets"]]:
        admin.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": settings.s3_region}
        )
    try:
        yield storage, admin
    finally:
        storage.close()
        admin.close()


def keys(admin, prefix):
    return {
        item["Key"]
        for page in admin.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix)
        for item in page.get("Contents", [])
    }


def generate(factory, engine, student, storage, renderer):
    _, result = fixed_result(student)

    class SyntheticUpstream:
        async def generate(self, command, report):
            return result

    command = replace(command_for(student), display_name="합성학생", narrative_enabled=True)
    service = GenerationService(
        factory,
        JobLocks(engine),
        RenderingGenerator(SyntheticUpstream(), renderer, storage),
        FakeCodec(command),
    )
    asyncio.run(service.generate(command))
    with factory() as session:
        report = (
            session.execute(select(weekly_report).where(weekly_report.c.job_id == command.job_id))
            .mappings()
            .one()
        )
        files = (
            session.execute(select(report_file).where(report_file.c.report_id == report["id"]))
            .mappings()
            .all()
        )
    return report, files, result


def test_render_store_download_revision_and_student_cleanup(
    minio_storage, minio_endpoint, report_factory, db_engine, report_student_id
):
    storage, admin = minio_storage
    first, first_files, _ = generate(
        report_factory, db_engine, report_student_id, storage, ReportRenderer()
    )
    first_keys = keys(admin, report_prefix(report_student_id, first["id"], 1))
    assert first["status"] == "COMPLETED" and len(first_files) == 3 and len(first_keys) == 6
    second, files, result = generate(
        report_factory, db_engine, report_student_id, storage, ReportRenderer()
    )
    assert second["status"] == "COMPLETED" and second["revision"] == 2
    assert len(files) == 3
    assert keys(admin, report_prefix(report_student_id, first["id"], 1)) == first_keys
    assert len(keys(admin, f"reports/{report_student_id}/")) == 12

    app = create_app()
    app.dependency_overrides[query_service] = lambda: QueryService(
        report_factory, None, lambda: storage, 300
    )
    urls = []
    with TestClient(app) as api, httpx.Client(timeout=10, trust_env=False) as http:
        for file in files:
            format = file["format"]
            for premium in (True, False):
                response = api.get(
                    f"/internal/reports/{second['id']}/files/{format.lower()}",
                    headers=headers(report_student_id, premium=premium),
                )
                assert response.status_code == 200
                signed = response.json()
                url = signed["url"]
                urls.append(url)
                assert url.startswith(minio_endpoint[1] + "/")
                assert parse_qs(urlsplit(url).query)["X-Amz-Expires"] == ["300"]
                assert datetime.fromisoformat(signed["expiresAt"]) > datetime.now(UTC)
                downloaded = http.get(url)
                assert downloaded.status_code == 200
                assert downloaded.headers["content-type"] == TYPES[format]
                assert downloaded.headers["cache-control"] == "private, no-store"
                assert downloaded.headers["content-disposition"] == (
                    f'attachment; filename="report-{second["id"]}-r2.{format.lower()}"'
                )
                if premium:
                    assert len(downloaded.content) == file["size_bytes"]
                text = (
                    "".join(
                        page.extract_text()
                        for page in PdfReader(io.BytesIO(downloaded.content)).pages
                    )
                    if format == "PDF"
                    else downloaded.text
                )
                normalized = re.sub(r"\s+", "", text)
                assert "합성학생" in normalized
                assert (re.sub(r"\s+", "", result.narrative["text"]) in normalized) == premium
                assert (result.evening_question.replace(" ", "") in normalized) == premium

        forbidden = api.get(
            f"/internal/reports/{second['id']}/files/pdf", headers=headers(uuid4(), premium=True)
        )
        assert forbidden.status_code == 403
        # A signature cannot be reused for the other audience or omitted entirely.
        assert http.get(urls[0].replace("/full/", "/free/")).status_code == 403
        assert http.get(urls[0].split("?", 1)[0]).status_code == 403
        other_key = report_key(uuid4(), uuid4(), 1, "PDF")
        storage.put(other_key, b"other synthetic student", "application/pdf")
        storage.delete_prefix(report_prefix(report_student_id, first["id"], 1))
        assert not keys(admin, report_prefix(report_student_id, first["id"], 1))
        assert len(keys(admin, f"reports/{report_student_id}/")) == 6
        storage.delete_prefix(f"reports/{report_student_id}/")
        assert not keys(admin, f"reports/{report_student_id}/")
        assert admin.head_object(Bucket=BUCKET, Key=other_key)["ContentLength"] > 0
        assert all(http.get(url).status_code == 404 for url in urls)
        unavailable = api.get(
            f"/internal/reports/{second['id']}/files/pdf", headers=headers(report_student_id)
        )
        assert unavailable.status_code == 503


def test_partial_minio_upload_denied_marks_failed_and_cleans_only_its_revision(
    minio_storage, minio_endpoint, report_factory, db_engine, report_student_id, monkeypatch
):
    storage, admin = minio_storage
    retained = report_key(report_student_id, uuid4(), 1, "PDF")
    storage.put(retained, b"previous synthetic revision", "application/pdf")
    bad = boto3.client(
        "s3",
        endpoint_url=minio_endpoint[0],
        region_name="ap-northeast-2",
        aws_access_key_id="invalid-synthetic-user",
        aws_secret_access_key="invalid-synthetic-secret",
        config=Config(signature_version="s3v4", retries={"total_max_attempts": 1}),
    )
    original_put, completed_uploads = storage.put, []
    denied = []

    def put(key, body, content_type):
        if len(completed_uploads) == 2:
            try:
                bad.put_object(Bucket=BUCKET, Key=key, Body=body)
            except bad.exceptions.ClientError as error:
                denied.append(error.response["ResponseMetadata"]["HTTPStatusCode"])
                raise
            pytest.fail("MinIO accepted invalid credentials")
        original_put(key, body, content_type)
        completed_uploads.append(key)

    monkeypatch.setattr(storage, "put", put)
    try:
        report, files, _ = generate(
            report_factory, db_engine, report_student_id, storage, FakeRenderer()
        )
    finally:
        bad.close()
    assert denied == [403] and len(completed_uploads) == 2
    assert report["status"] == "FAILED" and files == []
    assert keys(admin, f"reports/{report_student_id}/") == {retained}


def test_minio_rejects_expired_download_url(minio_storage):
    storage, _ = minio_storage
    student = uuid4()
    key = report_key(student, uuid4(), 1, "MD")
    storage.put(key, b"synthetic expiry check", TYPES["MD"])
    with httpx.Client(timeout=5, trust_env=False) as http:
        signed = storage.presigned_url(key, 5, "expiry.md")
        assert http.get(signed["url"]).status_code == 200
        # Bounded wait for server-side signature expiry (not a mocked SDK clock).
        time.sleep(6)
        response = http.get(signed["url"])
        assert response.status_code == 403 and "Request has expired" in response.text
    storage.delete_prefix(f"reports/{student}/")
