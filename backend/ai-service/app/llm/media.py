"""테마 그림·영상 생성 클라이언트와 영상 이어 붙이기.

#437, class-diagram 5.5 ImageClient·VideoClient.

- 그림: OpenAI images edits(참조 그림 여러 장). 사용량은 THEME_IMAGE로 기록(토큰은 응답 usage).
- 영상: Google Cloud Veo(첫 그림만 고정, 무음). THEME_VIDEO는 core enum에 들어가기 전이라
  사용량 이벤트를 보내지 않고 로그만 남긴다(ai.md 17.1 사용량). 운영 인증(WIF)은 인프라 확인 전이라
  접근 토큰을 설정으로 받는다(로컬 시험용).
- 컷 이어 붙이기(0.5초 녹아드는 전환)·장면 뽑기는 imageio-ffmpeg에 들어 있는 ffmpeg 실행 파일로
  한다(Docker 수정 없음).
- 시험은 가짜 구현(FakeImageClient·FakeVideoClient)을 쓴다.
"""

import asyncio
import base64
import logging
import re
import struct
import subprocess
import tempfile
import time
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import httpx
import imageio_ffmpeg
import openai

from app.config import Settings
from app.llm.base import LlmUnavailable, LlmUsage, UsageRecorder
from app.llm.providers import image_mime

logger = logging.getLogger(__name__)
IMAGE_CALL_TYPE = "THEME_IMAGE"
VEO_SIZE = (1280, 720)  # 요청 resolution 720p·16:9의 결과 크기(24fps, 실측)
STILL_ZOOM = 1.06  # 움직이는 그림 컷: 첫 그림을 컷 길이 동안 이 배율까지 천천히 확대


class ImageClient(Protocol):
    model: str

    async def edit(
        self, prompt: str, refs: Sequence[bytes], *, prompt_version: str, deadline: float
    ) -> bytes:
        """참조 그림(refs)을 넣어 새 그림 1장(PNG 바이트). refs가 비면 글로만 그린다."""
        ...


class VideoClient(Protocol):
    model: str
    size: tuple[int, int]  # 만드는 영상 크기(대체 컷을 같은 크기로 만들어 이어 붙이게)

    async def generate(
        self,
        prompt: str,
        first: bytes,
        last: bytes | None = None,
        *,
        seconds: int,
        deadline: float,
        negative: str | None = None,
    ) -> bytes:
        """첫 그림(first)을 고정한 무음 영상 1개(MP4 바이트). last가 있을 때만 끝 그림도 고정."""
        ...


def _remaining(deadline: float, cap: float) -> float:
    left = min(cap, deadline - time.monotonic())
    if left <= 0:
        raise LlmUnavailable("LLM_DEADLINE_EXCEEDED", retryable=True)
    return left


class OpenAIImageClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        size: str,
        quality: str,
        timeout: float,
        recorder: UsageRecorder,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self._size, self._quality, self._timeout = size, quality, timeout
        self._recorder = recorder
        self._client = client or openai.AsyncOpenAI(api_key=api_key, max_retries=0)

    async def edit(
        self, prompt: str, refs: Sequence[bytes], *, prompt_version: str, deadline: float
    ) -> bytes:
        timeout = _remaining(deadline, self._timeout)
        files = [
            (f"ref{i}.{image_mime(r).split('/')[1]}", r, image_mime(r)) for i, r in enumerate(refs)
        ]
        started = time.monotonic()
        usage = None
        try:
            if files:
                response = await self._client.images.edit(
                    model=self.model,
                    image=files,  # type: ignore[arg-type]
                    prompt=prompt,
                    size=self._size,  # type: ignore[arg-type]
                    quality=self._quality,  # type: ignore[arg-type]
                    n=1,
                    timeout=timeout,
                )
            else:  # 참조 그림이 없는 그림(뭉치·인물이 안 나오는 시작 첫 컷)은 글로만 생성
                response = await self._client.images.generate(
                    model=self.model,
                    prompt=prompt,
                    size=self._size,  # type: ignore[arg-type]
                    quality=self._quality,  # type: ignore[arg-type]
                    n=1,
                    timeout=timeout,
                )
            usage = response.usage
            data = response.data[0].b64_json if response.data else None
            if not data:
                raise LlmUnavailable("LLM_INVALID_OUTPUT", retryable=True)
            self._record(prompt_version, started, usage, None)
            return base64.b64decode(data)
        except openai.APIConnectionError as exc:
            code = "LLM_TIMEOUT" if isinstance(exc, openai.APITimeoutError) else "LLM_CONNECTION"
            self._record(prompt_version, started, usage, code)
            raise LlmUnavailable(code, retryable=True) from exc
        except openai.APIStatusError as exc:
            code, retryable = image_status(exc.status_code)
            self._record(prompt_version, started, usage, code)
            raise LlmUnavailable(code, retryable) from exc
        except LlmUnavailable as exc:
            self._record(prompt_version, started, usage, exc.code)
            raise

    def _record(self, version: str, started: float, usage: object, error: str | None) -> None:
        self._recorder(
            LlmUsage(
                call_type=IMAGE_CALL_TYPE,
                model=self.model,
                prompt_version=version,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                latency_ms=int((time.monotonic() - started) * 1000),
                success=error is None,
                error_code=error,
            )
        )


def image_status(status: int) -> tuple[str, bool]:
    if status == 429:
        return "LLM_RATE_LIMITED", True
    if status >= 500:
        return "LLM_SERVER_ERROR", True
    if status in (401, 403):
        return "LLM_AUTH_FAILED", False
    return "LLM_BAD_REQUEST", False  # 안전 정책 거절(400)도 여기. 그래프가 사유를 넣어 다시 만듦


class VeoVideoClient:
    """Veo REST(predictLongRunning → fetchPredictOperation 대기). 시험(2026-11-11)과 같은 호출.

    첫 그림만 고정한다(사용자 결정 2026-11-11). 끝 그림까지 고정하면 비슷한 두 그림 사이를
    억지로 이어 움직임이 흐물거리고 배경이 같아짐(실측). last를 주면 lastFrame도 보낸다.
    """

    def __init__(
        self,
        *,
        project: str,
        location: str,
        model: str,
        token: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
        poll_seconds: float = 8.0,
    ) -> None:
        self.model = model
        self.size = VEO_SIZE
        self._base = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/"
            f"{location}/publishers/google/models/{model}"
        )
        self._token, self._timeout, self._poll = token, timeout, poll_seconds
        self._client = client or httpx.AsyncClient(timeout=120)

    async def _post(self, url: str, body: dict) -> dict:
        try:
            response = await self._client.post(
                url, json=body, headers={"Authorization": f"Bearer {self._token}"}
            )
        except httpx.HTTPError as exc:
            raise LlmUnavailable("LLM_CONNECTION", retryable=True) from exc
        if response.status_code != 200:
            code, retryable = image_status(response.status_code)
            raise LlmUnavailable(code, retryable)
        return response.json()

    async def generate(
        self,
        prompt: str,
        first: bytes,
        last: bytes | None = None,
        *,
        seconds: int,
        deadline: float,
        negative: str | None = None,
    ) -> bytes:
        began = time.monotonic()
        limit = began + _remaining(deadline, self._timeout)

        def frame(data: bytes) -> dict:
            return {
                "bytesBase64Encoded": base64.b64encode(data).decode(),
                "mimeType": image_mime(data),
            }

        instance: dict = {"prompt": prompt, "image": frame(first)}
        if last is not None:
            instance["lastFrame"] = frame(last)
        parameters: dict = {
            "aspectRatio": "16:9",
            "durationSeconds": seconds,
            "sampleCount": 1,
            "resolution": "720p",
            "generateAudio": False,
        }
        if negative:
            parameters["negativePrompt"] = negative
        body = {"instances": [instance], "parameters": parameters}
        operation = await self._post(f"{self._base}:predictLongRunning", body)
        while time.monotonic() + self._poll < limit:
            await asyncio.sleep(self._poll)
            state = await self._post(
                f"{self._base}:fetchPredictOperation", {"operationName": operation["name"]}
            )
            if not state.get("done"):
                continue
            videos = (state.get("response") or {}).get("videos") or []
            if "error" in state or not videos:
                raise LlmUnavailable("LLM_INVALID_OUTPUT", retryable=True)
            logger.info(
                "theme video %ss model=%s in %.0fs", seconds, self.model, time.monotonic() - began
            )
            return base64.b64decode(videos[0]["bytesBase64Encoded"])
        raise LlmUnavailable("LLM_TIMEOUT", retryable=True)


# --- 가짜 구현(시험·설정 fake) ----------------------------------------------------


def tiny_png(seed: int = 0, width: int = 16, height: int = 9) -> bytes:
    """seed마다 색이 다른 작은 PNG(가짜 그림)."""
    color = bytes(((seed * 53) % 256, (seed * 97) % 256, (seed * 151) % 256))
    raw = b"".join(b"\x00" + color * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class FakeImageClient:
    def __init__(self, model: str = "fake-image") -> None:
        self.model = model
        self.calls: list[tuple[str, int]] = []  # (prompt, 참조 수)

    async def edit(
        self, prompt: str, refs: Sequence[bytes], *, prompt_version: str, deadline: float
    ) -> bytes:
        _remaining(deadline, 1e9)
        self.calls.append((prompt, len(refs)))
        return tiny_png(len(self.calls))


class FakeVideoClient:
    """ffmpeg로 만든 아주 작은 진짜 MP4(이어 붙이기·장면 뽑기까지 시험되게). 길이는 seconds."""

    def __init__(self, model: str = "fake-video") -> None:
        self.model = model
        self.size = (64, 36)  # color_clip 크기
        self.calls: list[tuple[str, bytes, bytes | None, int]] = []  # (지시문, 첫, 끝, 초)
        self.negatives: list[str | None] = []

    async def generate(
        self,
        prompt: str,
        first: bytes,
        last: bytes | None = None,
        *,
        seconds: int,
        deadline: float,
        negative: str | None = None,
    ) -> bytes:
        _remaining(deadline, 1e9)
        self.calls.append((prompt, first, last, seconds))
        self.negatives.append(negative)
        return await asyncio.to_thread(color_clip, len(self.calls), seconds)


# --- ffmpeg -------------------------------------------------------------------------


def _ffmpeg(args: list[str], timeout: float = 60) -> None:
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", *args],
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {result.stderr[-300:]!r}")


def color_clip(seed: int, seconds: float = 1.0, still: bool = False) -> bytes:
    """시험용 컷. 기본은 계속 움직이는 시험 무늬(멈춤 "
    "감지에 걸리지 않음), still이면 단색 정지 화면."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "c.mp4"
        color = f"0x{(seed * 53) % 256:02x}{(seed * 97) % 256:02x}{(seed * 151) % 256:02x}"
        source = f"color=c={color}:s=64x36:d={seconds}:r=12"
        if not still:  # 매 장면 달라지는 잡음(멈춤 감지에 걸리지 않음)
            source += ",noise=alls=80:allf=t+u"
        _ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                source,
                "-c:v",
                "mpeg4",
                "-pix_fmt",
                "yuv420p",
                str(out),
            ]
        )
        return out.read_bytes()


def still_clip(image: bytes, seconds: float, size: tuple[int, int]) -> bytes:
    """움직이는 그림 컷: 그림 1장을 seconds초 동안 가운데로 천천히 확대(24fps·yuv420p, size 크기).

    영상 컷이 끝내 검토를 통과하지 못하면 이 컷으로 대신한다(첫 그림은 그림 검토를 통과한 것).
    확대 떨림을 줄이려고 두 배로 키운 뒤 잘라 낸다.
    """
    width, height = size
    frames = max(1, round(seconds * 24))
    zoom = f"1+{STILL_ZOOM - 1:.3f}*on/{frames}"
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.img", Path(tmp) / "c.mp4"
        src.write_bytes(image)
        _ffmpeg(
            [
                "-i",
                str(src),
                "-vf",
                f"scale={width * 2}:{height * 2},zoompan=z='{zoom}':d={frames}"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps=24",
                "-frames:v",
                str(frames),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(out),
            ]
        )
        return out.read_bytes()


def concat_mp4(clips: Sequence[bytes]) -> bytes:
    """같은 형식 컷들을 순서대로 이어 한 파일로(다시 인코딩 없이 복사)."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        names = []
        for i, clip in enumerate(clips):
            path = folder / f"{i}.mp4"
            path.write_bytes(clip)
            names.append(f"file '{path.as_posix()}'")
        listing = folder / "list.txt"
        listing.write_text("\n".join(names), encoding="utf-8")
        out = folder / "out.mp4"
        _ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(out),
            ]
        )
        return out.read_bytes()


FADE_SECONDS = 0.5  # 컷 사이 녹아드는 전환 길이(사용자 결정 2026-11-11)


def xfade_starts(durations: Sequence[float], fade: float = FADE_SECONDS) -> list[float]:
    """녹아드는 전환으로 이은 영상에서 컷 i가 시작하는 시각 = 앞 컷 길이 합 - i × fade."""
    return [sum(durations[:i]) - i * fade for i in range(len(durations))]


def xfade_caption_times(
    durations: Sequence[float], fade: float = FADE_SECONDS
) -> list[tuple[float, float]]:
    """컷마다 문구를 띄울 (시작, 끝) 초. 경계는 겹치는 구간 한가운데(컷 시작 + fade/2).

    첫 컷은 0초부터, 마지막 컷은 영상 끝(컷 합 - 겹침)까지.
    """
    starts = xfade_starts(durations, fade)
    total = sum(durations) - (len(durations) - 1) * fade if durations else 0.0
    bounds = [0.0] + [s + fade / 2 for s in starts[1:]] + [total]
    return [(round(bounds[i], 2), round(bounds[i + 1], 2)) for i in range(len(durations))]


def join_xfade(
    clips: Sequence[bytes], durations: Sequence[float], fade: float = FADE_SECONDS
) -> bytes:
    """컷들을 fade초씩 겹쳐 녹아들게 이어 한 파일로(libx264·yuv420p·24fps로 다시 인코딩).

    길이 = 컷 길이 합 - (컷 수 - 1) × fade. 컷 길이는 요청한 길이(durations)를 쓴다.
    """
    if len(clips) != len(durations) or not clips:
        raise ValueError("컷 수와 길이 수가 같아야 함")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        inputs: list[str] = []
        for i, clip in enumerate(clips):
            path = folder / f"{i}.mp4"
            path.write_bytes(clip)
            inputs += ["-i", str(path)]
        parts = [
            f"[{i}:v]fps=24,format=yuv420p,setsar=1,settb=AVTB[v{i}]" for i in range(len(clips))
        ]
        last = "v0"
        starts = xfade_starts(durations, fade)
        for i in range(1, len(clips)):
            parts.append(
                f"[{last}][v{i}]xfade=transition=fade:duration={fade}:offset={starts[i]:.3f}[x{i}]"
            )
            last = f"x{i}"
        out = folder / "out.mp4"
        _ffmpeg(
            [
                *inputs,
                "-filter_complex",
                ";".join(parts),
                "-map",
                f"[{last}]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "24",
                "-an",
                "-movflags",
                "+faststart",
                str(out),
            ],
            timeout=180,
        )
        return out.read_bytes()


FREEZE_NOISE = 0.002  # freezedetect 잡음 허용(실측 Veo 컷의 멈춤 구간을 잡는 값)
FREEZE_MIN = 0.3  # 이보다 짧은 멈춤은 무시(초)


def freeze_spans(clip: bytes) -> tuple[float, list[tuple[float, float]]]:
    """(컷 길이, 화면이 멈춘 구간[(시작, 끝)]). ffmpeg freezedetect로 잰다."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(clip)
        result = subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-hide_banner",
                "-i",
                str(src),
                "-vf",
                f"freezedetect=n={FREEZE_NOISE}:d={FREEZE_MIN}",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=60,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {result.stderr[-300:]!r}")
    err = result.stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", err)]
    spans = [(s, ends[i] if i < len(ends) else duration) for i, s in enumerate(starts)]
    return duration, spans


def trim_clip(clip: bytes, start: float, end: float) -> bytes:
    """컷의 [start, end) 구간만 남김(libx264·yuv420p로 다시 인코딩)."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        src = folder / "in.mp4"
        src.write_bytes(clip)
        out = folder / "out.mp4"
        _ffmpeg(
            [
                "-i",
                str(src),
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(out),
            ]
        )
        return out.read_bytes()


def video_frames(clip: bytes, every: float = 2.0, count: int = 3) -> list[bytes]:
    """영상 검토용 장면 JPEG(every초마다, 6초 컷이면 0·2·4초 3장)."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        src = folder / "in.mp4"
        src.write_bytes(clip)
        _ffmpeg(
            [
                "-i",
                str(src),
                "-vf",
                f"fps=1/{every},scale=640:-2",
                "-q:v",
                "4",
                str(folder / "f%02d.jpg"),
            ]
        )
        return [p.read_bytes() for p in sorted(folder.glob("f*.jpg"))[:count]]


def create_media_clients(
    settings: Settings, recorder: UsageRecorder
) -> tuple[ImageClient | None, VideoClient | None]:
    """그림은 버킷이 있어야, 영상은 켜져 있고 프로젝트·토큰이 있어야 만든다(없으면 None: 건너뜀)."""
    image: ImageClient | None = None
    video: VideoClient | None = None
    if settings.asset_s3_bucket:
        if settings.image_provider == "fake":
            image = FakeImageClient()
        elif settings.openai_api_key:
            image = OpenAIImageClient(
                api_key=settings.openai_api_key,
                model=settings.image_model,
                size=settings.image_size,
                quality=settings.image_quality,
                timeout=settings.theme_image_timeout,
                recorder=recorder,
            )
    if image is not None and settings.theme_video_enabled:
        if settings.video_provider == "fake":
            video = FakeVideoClient()
        elif settings.video_project and settings.video_access_token:
            video = VeoVideoClient(
                project=settings.video_project,
                location=settings.video_location,
                model=settings.video_model,
                token=settings.video_access_token.get_secret_value(),
                timeout=settings.theme_video_timeout,
            )
    return image, video
