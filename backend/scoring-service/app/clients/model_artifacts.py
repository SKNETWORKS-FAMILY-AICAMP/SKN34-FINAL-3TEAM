"""S3 save_pretrained 디렉터리를 격리된 임시 경로로 다운로드한다."""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import boto3
from botocore.config import Config

from app.config import Settings


class S3ModelArtifacts:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self):
        # 자격 증명은 SDK 체인(환경 변수·IRSA 등)으로만 읽는다.
        return boto3.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            region_name=self._settings.s3_region,
            config=Config(
                connect_timeout=5,
                read_timeout=30,
                retries={"total_max_attempts": 1},
                s3={"addressing_style": "path"},
            ),
        )

    def _location(self, uri: str) -> tuple[str, str]:
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
        bucket, prefix = self._location(uri)
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
