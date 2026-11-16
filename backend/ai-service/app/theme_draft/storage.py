"""테마 그림·영상 S3 업로드 (class-diagram 5.5 ThemeStorage, #437).

report-service `clients/storage.py` 패턴(boto3, 자격 증명은 SDK 기본 체인, 소스에 키 없음).
실행마다 ID를 만들어 `theme-drafts/{실행 ID}/{장면}.png`·`.mp4`로 올리고 키만 돌려준다.
learning은 `theme-drafts/`로 시작하는 키만 같은 버킷(ASSET_S3_BUCKET)에서 presigned URL로 바꾼다.
"""

import asyncio
import re
import uuid
from typing import Protocol

from app.config import Settings

SCENES = ("INTRO", "MON", "TUE", "WED", "THU", "FRI", "OUTRO")
CONTENT_TYPE = {"png": "image/png", "mp4": "video/mp4"}
PREFIX = "theme-drafts"


def new_run_id() -> str:
    return uuid.uuid4().hex


def scene_key(run_id: str, scene: str, ext: str) -> str:
    """learning이 presign하는 키 형식(#438). 형식 밖 값은 올리지 않는다."""
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or scene not in SCENES or ext not in CONTENT_TYPE:
        raise ValueError(f"테마 자산 키 형식이 아님: {run_id}/{scene}.{ext}")
    return f"{PREFIX}/{run_id}/{scene}.{ext}"


class ThemeStorage(Protocol):
    async def put(self, key: str, body: bytes, content_type: str) -> None: ...


class S3ThemeStorage:
    def __init__(self, client, bucket: str) -> None:  # noqa: ANN001 (boto3 client)
        self._client, self._bucket = client, bucket

    @classmethod
    def configured(cls, settings: Settings) -> "S3ThemeStorage":
        import boto3
        from botocore.config import Config

        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"total_max_attempts": 2},
            connect_timeout=5,
            read_timeout=60,
        )
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            config=config,
        )
        return cls(client, settings.asset_s3_bucket or "")

    async def put(self, key: str, body: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            CacheControl="private, no-store",
        )


class MemoryThemeStorage:
    """시험·로컬 확인용(올린 키·바이트를 메모리에)."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = (body, content_type)


async def upload(storage: ThemeStorage, run_id: str, scene: str, ext: str, body: bytes) -> str:
    key = scene_key(run_id, scene, ext)
    await storage.put(key, body, CONTENT_TYPE[ext])
    return key


def create_storage(settings: Settings) -> ThemeStorage | None:
    """버킷이 비면 None(그림·영상 단계를 건너뜀)."""
    return S3ThemeStorage.configured(settings) if settings.asset_s3_bucket else None
