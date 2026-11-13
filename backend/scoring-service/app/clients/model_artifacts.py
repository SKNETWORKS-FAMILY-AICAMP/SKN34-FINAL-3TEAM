"""S3 save_pretrained 디렉터리 다운로드(격리된 임시 경로)와 사전 검사용 파일 정보 읽기."""

import base64
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings

STORAGE_CODES = {
    "404": "FILE_MISSING",
    "NoSuchKey": "FILE_MISSING",
    "403": "ACCESS_DENIED",
    "AccessDenied": "ACCESS_DENIED",
    "412": "OBJECT_CHANGED",
    "PreconditionFailed": "OBJECT_CHANGED",
}


class ArtifactError(Exception):
    """저장소 조회 실패. code: FILE_MISSING·ACCESS_DENIED·OBJECT_CHANGED·STORAGE_UNAVAILABLE"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@contextmanager
def _storage_errors() -> Iterator[None]:
    try:
        yield
    except ClientError as exc:
        error = str(exc.response.get("Error", {}).get("Code", ""))
        raise ArtifactError(STORAGE_CODES.get(error, "STORAGE_UNAVAILABLE")) from exc
    except (BotoCoreError, OSError) as exc:
        raise ArtifactError("STORAGE_UNAVAILABLE") from exc


@dataclass(frozen=True)
class ObjectHead:
    size: int
    etag: str | None
    # 파일 전체 SHA-256(hex). ETag·사용자 메타데이터·multipart COMPOSITE는 파일 해시가 아니라 None
    sha256: str | None


class ArtifactReader:
    """모델 디렉터리 한 곳의 파일 정보·작은 파일 본문 읽기 (가중치 본문은 받지 않는다)."""

    def __init__(self, client, bucket: str, prefix: str) -> None:
        self._client, self._bucket, self._prefix = client, bucket, prefix

    def head(self, file: str) -> ObjectHead:
        with _storage_errors():
            head = self._client.head_object(
                Bucket=self._bucket, Key=self._prefix + file, ChecksumMode="ENABLED"
            )
        checksum = head.get("ChecksumSHA256", "")
        sha256 = None
        if head.get("ChecksumType") != "COMPOSITE" and checksum:
            try:
                sha256 = base64.b64decode(checksum, validate=True).hex()
            except ValueError:
                sha256 = None
        return ObjectHead(head["ContentLength"], head.get("ETag"), sha256)

    def read(self, file: str, head: ObjectHead, limit: int) -> bytes:
        """head 이후 바뀌지 않은 파일만 limit 바이트까지 읽는다."""
        if head.etag is None:
            raise KeyError("ETag")
        with _storage_errors():
            response = self._client.get_object(
                Bucket=self._bucket, Key=self._prefix + file, IfMatch=head.etag
            )
            with closing(response["Body"]) as body:
                return body.read(limit)


class S3ModelArtifacts:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self, connect_timeout=5, read_timeout=30):
        # 자격 증명은 SDK 체인(환경 변수·IRSA 등)으로만 읽는다.
        return boto3.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            region_name=self._settings.s3_region,
            config=Config(
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                retries={"total_max_attempts": 1},
                s3={"addressing_style": "path"},
            ),
        )

    def location(self, uri: str) -> tuple[str, str]:
        parsed = urlsplit(uri)
        prefix = parsed.path.lstrip("/")
        if (
            parsed.scheme != "s3"
            or parsed.netloc != self._settings.s3_bucket
            or parsed.query
            or parsed.fragment
            or not prefix
            or not prefix.endswith("/")
        ):
            raise ValueError("expected S3 directory in configured model bucket")
        return parsed.netloc, prefix

    @contextmanager
    def reader(self, uri: str, connect_timeout=5, read_timeout=30) -> Iterator[ArtifactReader]:
        bucket, prefix = self.location(uri)
        with closing(self._client(connect_timeout=connect_timeout, read_timeout=read_timeout)) as c:
            yield ArtifactReader(c, bucket, prefix)

    @staticmethod
    def _relative_key(key: str, prefix: str) -> Path:
        if not key.startswith(prefix):
            raise ValueError("object outside model prefix")
        relative = key[len(prefix) :]
        parts = relative.split("/")
        if (
            not relative
            or "\\" in relative
            or ":" in relative
            or PurePosixPath(relative).is_absolute()
            or any(p in {"", ".", ".."} for p in parts)
            or any(p.endswith((".", " ")) or PureWindowsPath(p).is_reserved() for p in parts)
        ):
            raise ValueError("unsafe model object key")
        return Path(*parts)

    @contextmanager
    def download(self, uri: str) -> Iterator[Path]:
        bucket, prefix = self.location(uri)
        root = self._settings.model_cache_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        # 새 작업 디렉터리만 정리한다. 기존 사용자 파일이나 다른 다운로드는 건드리지 않는다.
        with TemporaryDirectory(prefix="loading-", dir=root) as directory:
            target = Path(directory)
            with closing(self._client()) as client:
                count = 0
                for page in client.get_paginator("list_objects_v2").paginate(
                    Bucket=bucket, Prefix=prefix
                ):
                    for item in page.get("Contents", []):
                        key = item["Key"]
                        if key.endswith("/"):
                            continue
                        path = target / self._relative_key(key, prefix)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        client.download_file(bucket, key, str(path))
                        count += 1
                if not count:
                    raise ValueError("empty model directory")
            yield target
