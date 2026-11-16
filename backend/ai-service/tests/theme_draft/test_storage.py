"""테마 그림·영상 S3 키 형식과 업로드(메모리 저장소). 실제 S3는 부르지 않는다."""

import asyncio
import re

import pytest

from app.config import get_settings
from app.theme_draft.storage import (
    MemoryThemeStorage,
    create_storage,
    new_run_id,
    scene_key,
    upload,
)


def test_scene_key_format_learning_presigns() -> None:
    run_id = new_run_id()
    assert re.fullmatch(r"[0-9a-f]{32}", run_id)
    assert scene_key(run_id, "INTRO", "mp4") == f"theme-drafts/{run_id}/INTRO.mp4"
    assert scene_key(run_id, "MON", "png") == f"theme-drafts/{run_id}/MON.png"


@pytest.mark.parametrize(
    ("run_id", "scene", "ext"),
    [
        ("../etc", "MON", "png"),  # 실행 ID 형식 밖
        ("a" * 32, "INTRO1", "png"),  # 컷 그림은 올리지 않음(장면 7개만)
        ("a" * 32, "MON", "jpg"),
    ],
)
def test_scene_key_rejects_other_shapes(run_id: str, scene: str, ext: str) -> None:
    with pytest.raises(ValueError):
        scene_key(run_id, scene, ext)


def test_upload_puts_with_content_type() -> None:
    storage, run_id = MemoryThemeStorage(), new_run_id()
    key = asyncio.run(upload(storage, run_id, "OUTRO", "mp4", b"video"))
    assert storage.objects == {key: (b"video", "video/mp4")}


def test_no_bucket_no_storage() -> None:
    assert create_storage(get_settings().model_copy(update={"asset_s3_bucket": None})) is None
