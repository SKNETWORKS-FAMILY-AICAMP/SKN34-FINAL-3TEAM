"""테마 그림·영상 S3 업로드 (class-diagram 5.5 ThemeStorage, #437).

report-service `clients/storage.py` 패턴(boto3, 자격 증명은 SDK 기본 체인, 소스에 키 없음).
실행마다 ID를 만들어 `theme-drafts/{실행 ID}/{장면}.png`·`.mp4`로 올리고 키만 돌려준다.
learning은 `theme-drafts/`로 시작하는 키만 같은 버킷(ASSET_S3_BUCKET)에서 presigned URL로 바꾼다.

부분 다시 생성 재료(#537): 테마 옷 뭉치 `OUTFIT.png`와 컷 첫 그림 `INTRO1~6.png`·`OUTRO1~6.png`·
끝 표정 그림
`INTRO5END.png` 등(#779)도
같은
실행 폴더에 올리고, 부분 다시 생성 때 `get`으로 다시 읽는다(ai 역할에 GetObject 필요, 사용자 결정
2026-11-17). 보관 기간은 따로 두지 않는다(지우지 않음).
"""

import asyncio
import re
import uuid
from typing import Protocol

from app.config import Settings
from app.theme_draft.cuts import END_FACE as END

SCENES = ("INTRO", "MON", "TUE", "WED", "THU", "FRI", "OUTRO")
# 부분 다시 생성 재료 그림(#537): 테마 옷 뭉치와 시작·종료 컷 첫 그림, 인물만 그린 인물 기준
# 그림(CHARS, #779). regen.assets는 ai 전용 칸이라 learning은 이름을 보지 않음. 컷은 6컷 틀까지
# (#779 2026-11-19, 예전 초안은 1~4)
# 표정 그림 두 장 컷의 끝 그림(INTRO5END 등, #779 사용자 결정 2026-11-20 A안)도 재료
ASSETS = (
    "OUTFIT",
    "CHARS",
    *(f"{s}{i}{e}" for s in ("INTRO", "OUTRO") for i in range(1, 7) for e in ("", END)),
)
CONTENT_TYPE = {"png": "image/png", "mp4": "video/mp4"}
PREFIX = "theme-drafts"


def new_run_id() -> str:
    return uuid.uuid4().hex


def scene_key(run_id: str, scene: str, ext: str) -> str:
    """learning이 presign하는 키 형식(#438). 형식 밖 값은 올리지 않는다. 재료 그림은 .png만."""
    known = scene in SCENES or (scene in ASSETS and ext == "png")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or not known or ext not in CONTENT_TYPE:
        raise ValueError(f"테마 자산 키 형식이 아님: {run_id}/{scene}.{ext}")
    return f"{PREFIX}/{run_id}/{scene}.{ext}"


class ThemeStorage(Protocol):
    async def put(self, key: str, body: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...


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

    async def get(self, key: str) -> bytes:
        """`theme-drafts/` 키만 읽는다(부분 다시 생성 재료, #537)."""
        if not key.startswith(f"{PREFIX}/"):
            raise ValueError(f"테마 자산 키가 아님: {key}")

        def read() -> bytes:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

        return await asyncio.to_thread(read)


class MemoryThemeStorage:
    """시험·로컬 확인용(올린 키·바이트를 메모리에)."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = (body, content_type)

    async def get(self, key: str) -> bytes:
        return self.objects[key][0]


async def upload(storage: ThemeStorage, run_id: str, scene: str, ext: str, body: bytes) -> str:
    key = scene_key(run_id, scene, ext)
    await storage.put(key, body, CONTENT_TYPE[ext])
    return key


def create_storage(settings: Settings) -> ThemeStorage | None:
    """버킷이 비면 None(그림·영상 단계를 건너뜀)."""
    return S3ThemeStorage.configured(settings) if settings.asset_s3_bucket else None
