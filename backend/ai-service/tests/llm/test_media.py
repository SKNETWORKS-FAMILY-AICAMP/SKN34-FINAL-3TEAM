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

import google.auth.exceptions
import httpx
import imageio_ffmpeg
import pytest

from app.config import get_settings
from app.llm import media
from app.llm.base import LlmUnavailable, LlmUsage
from app.llm.media import (
    FakeImageClient,
    FakeVideoClient,
    GoogleTokenSource,
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
        client.generate(
            "동작",
            b"first",
            seconds=4,
            prompt_version="v",
            deadline=time.monotonic() + 30,
            negative="n",
        )
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


class StaticTokens:
    def __init__(self, token: str = "t") -> None:
        self._token = token

    async def token(self) -> str:
        return self._token


def veo_client(
    seen: list[dict],
    auth: list[str] | None = None,
    usages: list[LlmUsage] | None = None,
    start_status: int = 200,
    done: dict | None = None,
) -> VeoVideoClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if auth is not None:
            auth.append(request.headers["Authorization"])
        if request.url.path.endswith(":predictLongRunning"):
            return httpx.Response(start_status, json={"name": "op-1"})
        video = base64.b64encode(b"mp4-bytes").decode()
        return httpx.Response(
            200,
            json=done or {"done": True, "response": {"videos": [{"bytesBase64Encoded": video}]}},
        )

    return VeoVideoClient(
        project="p",
        location="us-central1",
        model="veo-fast",
        tokens=StaticTokens(),
        timeout=30,
        recorder=(usages if usages is not None else []).append,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        poll_seconds=0.01,
    )


def test_veo_fixes_first_frame_only_with_negative_prompt() -> None:
    seen: list[dict] = []
    auth: list[str] = []
    clip = asyncio.run(
        veo_client(seen, auth).generate(
            "동작",
            tiny_png(1),
            seconds=8,
            prompt_version="v",
            deadline=time.monotonic() + 30,
            negative="big eyes",
        )
    )
    assert clip == b"mp4-bytes"
    instance, parameters = seen[0]["instances"][0], seen[0]["parameters"]
    assert set(instance) == {"prompt", "image"}  # lastFrame 없음
    assert parameters["negativePrompt"] == "big eyes" and parameters["durationSeconds"] == 8
    assert seen[1] == {"operationName": "op-1"}
    assert auth == ["Bearer t", "Bearer t"]  # 시작·대기 요청마다 토큰 공급자에서 받음


def test_veo_sends_last_frame_only_when_given() -> None:
    seen: list[dict] = []
    asyncio.run(
        veo_client(seen).generate(
            "동작",
            tiny_png(1),
            tiny_png(2),
            seconds=6,
            prompt_version="v",
            deadline=time.monotonic() + 30,
        )
    )
    assert "lastFrame" in seen[0]["instances"][0]
    assert "negativePrompt" not in seen[0]["parameters"]


def test_veo_records_theme_video_usage_per_cut_without_tokens() -> None:
    usages: list[LlmUsage] = []
    asyncio.run(
        veo_client([], usages=usages).generate(
            "동작", tiny_png(1), seconds=4, prompt_version="theme@3", deadline=time.monotonic() + 30
        )
    )
    # 시작·대기 요청 2번이어도 컷 1개에 1건. 초 단위 과금이라 토큰은 null(core 미산정)
    assert usages == [
        LlmUsage("THEME_VIDEO", "veo-fast", "theme@3", None, None, usages[0].latency_ms, True, None)
    ]


@pytest.mark.parametrize(
    ("start_status", "done", "timeout", "code"),
    [
        (429, None, 30, "LLM_RATE_LIMITED"),
        (200, {"done": True, "error": {"code": 3}}, 30, "LLM_INVALID_OUTPUT"),
        (200, {"done": False}, 0.05, "LLM_TIMEOUT"),  # 끝나지 않는 작업만 금방 시간 초과
    ],
)
def test_veo_records_failed_cut(
    start_status: int, done: dict | None, timeout: float, code: str
) -> None:
    usages: list[LlmUsage] = []
    client = veo_client([], usages=usages, start_status=start_status, done=done)
    client._timeout = timeout
    with pytest.raises(LlmUnavailable) as caught:
        asyncio.run(
            client.generate(
                "동작", tiny_png(1), seconds=4, prompt_version="v", deadline=time.monotonic() + 30
            )
        )
    assert caught.value.code == code
    assert [(u.call_type, u.success, u.error_code) for u in usages] == [
        ("THEME_VIDEO", False, code)
    ]


def test_veo_deadline_passed_before_call_records_nothing() -> None:
    usages: list[LlmUsage] = []
    with pytest.raises(LlmUnavailable):
        asyncio.run(
            veo_client([], usages=usages).generate(
                "동작", tiny_png(1), seconds=4, prompt_version="v", deadline=time.monotonic() - 1
            )
        )
    assert usages == []  # 요청을 보내지 않았으니 사용량도 없음(그림과 같음)


class FakeCredentials:
    """google-auth 자격 증명 흉내(valid·token·refresh). 갱신 횟수를 센다."""

    def __init__(self, *, valid: bool, error: Exception | None = None) -> None:
        self.valid = valid
        self.token: str | None = "old" if valid else None
        self.refreshes = 0
        self._error = error

    def refresh(self, request: object) -> None:
        time.sleep(0.01)  # 동시 요청이 갱신 중에 겹치게
        self.refreshes += 1
        if self._error is not None:
            raise self._error
        self.token, self.valid = f"new-{self.refreshes}", True


def test_google_tokens_refresh_only_when_invalid() -> None:
    fresh = FakeCredentials(valid=True)
    assert asyncio.run(GoogleTokenSource(fresh).token()) == "old"  # type: ignore[arg-type]
    assert fresh.refreshes == 0
    stale = FakeCredentials(valid=False)
    assert asyncio.run(GoogleTokenSource(stale).token()) == "new-1"  # type: ignore[arg-type]


def test_google_tokens_refresh_once_for_concurrent_cuts() -> None:
    stale = FakeCredentials(valid=False)
    source = GoogleTokenSource(stale)  # type: ignore[arg-type]

    async def four_cuts() -> list[str]:
        return await asyncio.gather(*(source.token() for _ in range(4)))

    assert asyncio.run(four_cuts()) == ["new-1"] * 4
    assert stale.refreshes == 1


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (google.auth.exceptions.RefreshError("revoked"), "LLM_AUTH_FAILED", False),
        (google.auth.exceptions.TransportError("down"), "LLM_CONNECTION", True),
    ],
)
def test_google_tokens_refresh_failure(error: Exception, code: str, retryable: bool) -> None:
    source = GoogleTokenSource(FakeCredentials(valid=False, error=error))  # type: ignore[arg-type]
    with pytest.raises(LlmUnavailable) as caught:
        asyncio.run(source.token())
    assert (caught.value.code, caught.value.retryable) == (code, retryable)


def test_create_media_clients_veo_needs_google_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings().model_copy(
        update={
            "asset_s3_bucket": "b",
            "image_provider": "fake",
            "theme_video_enabled": True,
            "video_provider": "veo",
            "video_project": "p",
        }
    )

    def missing(**_: object) -> tuple[object, str]:
        raise google.auth.exceptions.DefaultCredentialsError("none")

    monkeypatch.setattr(media.google.auth, "default", missing)
    assert create_media_clients(settings, print)[1] is None  # 자격 증명 없으면 영상만 건너뜀

    found: dict[str, object] = {}

    def default(**kwargs: object) -> tuple[object, str]:
        found.update(kwargs)
        return FakeCredentials(valid=True), "p"

    monkeypatch.setattr(media.google.auth, "default", default)
    image, video = create_media_clients(settings, print)
    assert isinstance(image, FakeImageClient) and isinstance(video, VeoVideoClient)
    assert video._recorder is print  # 사용량 기록기를 영상 클라이언트에도 넘김
    assert found["scopes"] == ("https://www.googleapis.com/auth/cloud-platform",)
    no_project = settings.model_copy(update={"video_project": None})
    assert create_media_clients(no_project, print)[1] is None


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
