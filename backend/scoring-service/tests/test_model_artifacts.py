from pathlib import Path

import pytest

from app.clients.model_artifacts import S3ModelArtifacts
from app.config import Settings

PREFIX = "models/m2-klue-narrative/1.0/"
URI = "s3://sagomungchi-local-models/" + PREFIX


class S3Double:
    def __init__(self, keys, fail=False):
        self.keys = keys
        self.fail = fail
        self.downloads = []
        self.prefix = None
        self.closed = False

    def close(self):
        self.closed = True

    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        return self

    def paginate(self, **kwargs):
        self.prefix = kwargs["Prefix"]
        # 여러 페이지에 나뉜 파일도 모두 내려받는다.
        for key in self.keys:
            yield {"Contents": [{"Key": key}]}

    def download_file(self, bucket, key, filename):
        self.downloads.append(key)
        Path(filename).write_bytes(b"synthetic bytes")
        if self.fail:
            raise OSError("download interrupted")


def make_artifacts(tmp_path, monkeypatch, client):
    artifacts = S3ModelArtifacts(Settings(model_cache_dir=tmp_path))
    monkeypatch.setattr(artifacts, "_client", lambda: client)
    return artifacts


def test_download_all_pages_and_clean_only_own_temporary_directory(tmp_path, monkeypatch):
    keep = tmp_path / "existing.txt"
    keep.write_text("keep")
    s3 = S3Double([PREFIX, PREFIX + "config.json", PREFIX + "nested/tokenizer.json"])
    artifacts = make_artifacts(tmp_path, monkeypatch, s3)
    with artifacts.download(URI) as directory:
        assert (directory / "config.json").read_bytes() == b"synthetic bytes"
        assert (directory / "nested/tokenizer.json").exists()
        assert s3.prefix == PREFIX
    assert not directory.exists()
    assert s3.closed
    assert keep.read_text() == "keep"


@pytest.mark.parametrize(
    "relative",
    [
        "../outside",
        "/absolute",
        "a/../../x",
        "a\\b",
        "C:/x",
        "a:stream",
        "NUL",
        "a/./b",
        "a//b",
        "a.",
    ],
)
def test_reject_paths_outside_directory(tmp_path, monkeypatch, relative):
    artifacts = make_artifacts(tmp_path, monkeypatch, S3Double([PREFIX + relative]))
    with pytest.raises(ValueError):
        with artifacts.download(URI):
            pytest.fail("unsafe path was accepted")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "uri",
    [
        "https://host/model",
        "s3://another-bucket/model/",
        "s3://sagomungchi-local-models/",
        URI.rstrip("/"),
        URI + "?secret=x",
    ],
)
def test_reject_unapproved_bucket_or_non_directory(tmp_path, monkeypatch, uri):
    artifacts = make_artifacts(tmp_path, monkeypatch, S3Double([]))
    with pytest.raises(ValueError):
        with artifacts.download(uri):
            pytest.fail("invalid URI was accepted")


def test_empty_or_interrupted_download_not_reused(tmp_path, monkeypatch):
    for client, error in [
        (S3Double([]), ValueError),
        (S3Double([PREFIX + "weights"], fail=True), OSError),
    ]:
        artifacts = make_artifacts(tmp_path, monkeypatch, client)
        with pytest.raises(error):
            with artifacts.download(URI):
                pytest.fail("incomplete download was accepted")
        assert list(tmp_path.iterdir()) == []
