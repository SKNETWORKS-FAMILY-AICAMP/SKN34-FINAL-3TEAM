"""테마 그림·영상 클라이언트와 ffmpeg 도우미 시험. 실제 OpenAI·Google은 부르지 않는다."""

import asyncio
import base64
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import imageio_ffmpeg
import pytest

from app.config import get_settings
from app.llm.base import LlmUnavailable, LlmUsage
from app.llm.media import (
    FakeImageClient,
    FakeVideoClient,
    OpenAIImageClient,
    VeoVideoClient,
    color_clip,
    create_media_clients,
    join_xfade,
    tiny_png,
    video_frames,
    xfade_caption_times,
    xfade_starts,
)


def seconds_of(data: bytes) -> float:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "v.mp4"
        path.write_bytes(data)
        err = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)],
            capture_output=True,
            text=True,
            check=False,
        ).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()  # type: ignore[union-attr]
    return int(h) * 3600 + int(m) * 60 + float(s)


def test_fake_image_client_records_and_respects_deadline() -> None:
    client = FakeImageClient()
    image = asyncio.run(
        client.edit("그림", [b"a", b"b"], prompt_version="v", deadline=time.monotonic() + 10)
    )
    assert image.startswith(b"\x89PNG") and client.calls == [("그림", 2)]
    with pytest.raises(LlmUnavailable):
        asyncio.run(client.edit("그림", [], prompt_version="v", deadline=time.monotonic() - 1))


def test_fake_video_client_makes_clip_of_requested_length() -> None:
    client = FakeVideoClient()
    clip = asyncio.run(
        client.generate("동작", b"first", seconds=4, deadline=time.monotonic() + 30, negative="n")
    )
    assert client.calls == [("동작", b"first", None, 4)] and client.negatives == ["n"]
    assert seconds_of(clip) == pytest.approx(4, abs=0.1)


def test_join_xfade_length_is_sum_minus_overlaps() -> None:
    durations = [4, 6, 8, 6]
    clips = [color_clip(i, s) for i, s in enumerate(durations)]
    joined = join_xfade(clips, durations)
    assert seconds_of(joined) == pytest.approx(sum(durations) - 3 * 0.5, abs=0.15)
    with pytest.raises(ValueError):
        join_xfade(clips, durations[:3])


def test_caption_times_split_at_overlap_middle() -> None:
    assert xfade_starts([4, 6, 8, 6]) == [0, 3.5, 9.0, 16.5]
    assert xfade_caption_times([4, 6, 8, 6]) == [
        (0.0, 3.75),
        (3.75, 9.25),
        (9.25, 16.75),
        (16.75, 22.5),
    ]
    assert xfade_caption_times([6], fade=0.5) == [(0.0, 6.0)]


def test_video_frames_every_two_seconds() -> None:
    frames = video_frames(color_clip(1, 8), every=2.0, count=4)
    assert len(frames) == 4 and all(f[:3] == b"\xff\xd8\xff" for f in frames)  # JPEG


class FakeImages:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def _reply(self, kind: str, kwargs: dict) -> SimpleNamespace:
        self.calls.append((kind, kwargs))
        data = base64.b64encode(tiny_png(3)).decode()
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=11, output_tokens=22),
            data=[SimpleNamespace(b64_json=data)],
        )

    async def edit(self, **kwargs: object) -> SimpleNamespace:
        return await self._reply("edit", kwargs)

    async def generate(self, **kwargs: object) -> SimpleNamespace:
        return await self._reply("generate", kwargs)


def test_openai_image_client_edits_with_refs_and_generates_without() -> None:
    images, usages = FakeImages(), []
    client = OpenAIImageClient(
        api_key="sk-not-used",
        model="img-model",
        size="1536x864",
        quality="medium",
        timeout=30,
        recorder=usages.append,
        client=SimpleNamespace(images=images),  # type: ignore[arg-type]
    )
    deadline = time.monotonic() + 30
    asyncio.run(client.edit("고치기", [tiny_png(1)], prompt_version="v", deadline=deadline))
    out = asyncio.run(client.edit("새로", [], prompt_version="v", deadline=deadline))
    assert out == tiny_png(3)
    assert [k for k, _ in images.calls] == ["edit", "generate"]  # 참조가 없으면 글로만
    assert "image" not in images.calls[1][1] and images.calls[1][1]["size"] == "1536x864"
    assert usages[0] == LlmUsage(
        "THEME_IMAGE", "img-model", "v", 11, 22, usages[0].latency_ms, True, None
    )


def veo_client(seen: list[dict]) -> VeoVideoClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if request.url.path.endswith(":predictLongRunning"):
            return httpx.Response(200, json={"name": "op-1"})
        video = base64.b64encode(b"mp4-bytes").decode()
        return httpx.Response(
            200, json={"done": True, "response": {"videos": [{"bytesBase64Encoded": video}]}}
        )

    return VeoVideoClient(
        project="p",
        location="us-central1",
        model="veo-fast",
        token="t",
        timeout=30,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        poll_seconds=0.01,
    )


def test_veo_fixes_first_frame_only_with_negative_prompt() -> None:
    seen: list[dict] = []
    clip = asyncio.run(
        veo_client(seen).generate(
            "동작", tiny_png(1), seconds=8, deadline=time.monotonic() + 30, negative="big eyes"
        )
    )
    assert clip == b"mp4-bytes"
    instance, parameters = seen[0]["instances"][0], seen[0]["parameters"]
    assert set(instance) == {"prompt", "image"}  # lastFrame 없음
    assert parameters["negativePrompt"] == "big eyes" and parameters["durationSeconds"] == 8
    assert seen[1] == {"operationName": "op-1"}


def test_veo_sends_last_frame_only_when_given() -> None:
    seen: list[dict] = []
    asyncio.run(
        veo_client(seen).generate(
            "동작", tiny_png(1), tiny_png(2), seconds=6, deadline=time.monotonic() + 30
        )
    )
    assert "lastFrame" in seen[0]["instances"][0]
    assert "negativePrompt" not in seen[0]["parameters"]


def test_create_media_clients_needs_bucket_and_video_switch() -> None:
    base = get_settings()
    assert create_media_clients(base.model_copy(update={"asset_s3_bucket": None}), print) == (
        None,
        None,
    )
    fake = base.model_copy(
        update={"asset_s3_bucket": "b", "image_provider": "fake", "video_provider": "fake"}
    )
    image, video = create_media_clients(
        fake.model_copy(update={"theme_video_enabled": False}), print
    )
    assert isinstance(image, FakeImageClient) and video is None  # 영상 기본 꺼짐
    image, video = create_media_clients(
        fake.model_copy(update={"theme_video_enabled": True}), print
    )
    assert isinstance(video, FakeVideoClient)
