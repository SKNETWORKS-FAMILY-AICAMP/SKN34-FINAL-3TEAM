"""테마 그림·영상 생성 클라이언트와 영상 이어 붙이기.

#437, class-diagram 5.5 ImageClient·VideoClient.

- 그림: OpenAI images edits(참조 그림 여러 장). 사용량은 THEME_IMAGE로 기록(토큰은 응답 usage).
- 영상: Google Cloud Veo(첫 그림만 고정, 무음). 사용량은 컷 호출마다 THEME_VIDEO로 기록(#546).
  Veo는 토큰이 아니라 초 단위 과금이라 토큰은 null(core costUsd null, 미산정). 인증은 Google 표준
  자격 증명(`google.auth.default()`, #538): 운영은 GOOGLE_APPLICATION_CREDENTIALS가 가리키는
  파일(서비스 계정 키 또는 WIF 설정), 로컬은 `gcloud auth application-default login`. 토큰은 만료
  전에 갱신.
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

import google.auth
import google.auth.credentials
import google.auth.exceptions
import google.auth.transport.requests
import httpx
import imageio_ffmpeg
import openai

from app.config import Settings
from app.llm.base import LlmUnavailable, LlmUsage, UsageRecorder
from app.llm.providers import image_mime

logger = logging.getLogger(__name__)
IMAGE_CALL_TYPE = "THEME_IMAGE"
VIDEO_CALL_TYPE = "THEME_VIDEO"
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
        prompt_version: str,
        deadline: float,
        negative: str | None = None,
    ) -> bytes:
        """첫 그림(first)을 고정한 무음 영상 1개(MP4 바이트). last가 있을 때만 끝 그림도 고정."""
        ...

    async def generate_many(
        self,
        prompt: str,
        first: bytes,
        *,
        count: int,
        seconds: int,
        prompt_version: str,
        deadline: float,
        negative: str | None = None,
    ) -> list[bytes]:
        """같은 지시·첫 그림으로 후보 영상 최대 count개(한 번 호출, #779). 안전 필터로 일부가
        빠지면 count보다 적을 수 있고, 하나도 없으면 LlmUnavailable."""
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


GOOGLE_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)


class TokenSource(Protocol):
    async def token(self) -> str:
        """요청에 붙일 접근 토큰(만료 전이면 그대로, 아니면 갱신해서)."""
        ...


class GoogleTokenSource:
    """Google 자격 증명(google.auth.default)에서 접근 토큰을 꺼내고 만료 전에 갱신한다.

    google-auth의 `valid`는 만료 몇 분 전부터 거짓이 되므로 그때 갱신한다. 갱신은 동기 호출이라
    스레드에서 하고, 컷 여러 개가 동시에 요청해도 한 번만 갱신하게 잠근다.
    """

    def __init__(self, credentials: google.auth.credentials.Credentials) -> None:
        self._credentials = credentials
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        async with self._lock:
            if not self._credentials.valid:
                request = google.auth.transport.requests.Request()
                try:
                    await asyncio.to_thread(self._credentials.refresh, request)
                except google.auth.exceptions.RefreshError as exc:
                    raise LlmUnavailable("LLM_AUTH_FAILED", retryable=False) from exc
                except google.auth.exceptions.TransportError as exc:
                    raise LlmUnavailable("LLM_CONNECTION", retryable=True) from exc
            return str(self._credentials.token)


def google_token_source() -> GoogleTokenSource | None:
    """표준 자격 증명을 찾으면 토큰 공급자, 없으면 None(영상 건너뜀)."""
    try:
        credentials, _ = google.auth.default(scopes=GOOGLE_SCOPES)
    except google.auth.exceptions.DefaultCredentialsError:
        return None
    return GoogleTokenSource(credentials)


class VeoVideoClient:
    """Veo REST(predictLongRunning → fetchPredictOperation 대기). 시험(2026-11-11)과 같은 호출.

    첫 그림만 고정한다(사용자 결정 2026-11-11). 끝 그림까지 고정하면 비슷한 두 그림 사이를
    억지로 이어 움직임이 흐물거리고 배경이 같아짐(실측). last를 주면 lastFrame도 보낸다.
    토큰은 요청마다 tokens에서 받는다(대기 중에 만료돼도 갱신됨).
    사용량은 컷 1개(시작부터 결과 또는 실패까지)마다 THEME_VIDEO 1건(그림과 같은 방식).
    #779: generate_many는 sampleCount로 후보 여러 개를 한 번에 받는다(사용량도 호출 1건, Veo 비용은
    후보 수 × 초).
    """

    def __init__(
        self,
        *,
        project: str,
        location: str,
        model: str,
        tokens: TokenSource,
        timeout: float,
        recorder: UsageRecorder,
        client: httpx.AsyncClient | None = None,
        poll_seconds: float = 8.0,
    ) -> None:
        self.model = model
        self.size = VEO_SIZE
        self._base = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/"
            f"{location}/publishers/google/models/{model}"
        )
        self._tokens, self._timeout, self._poll = tokens, timeout, poll_seconds
        self._recorder = recorder
        self._client = client or httpx.AsyncClient(timeout=120)

    async def _post(self, url: str, body: dict) -> dict:
        token = await self._tokens.token()
        try:
            response = await self._client.post(
                url, json=body, headers={"Authorization": f"Bearer {token}"}
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
        prompt_version: str,
        deadline: float,
        negative: str | None = None,
    ) -> bytes:
        clips = await self._call(
            prompt, first, last, 1, seconds, prompt_version, deadline, negative
        )
        return clips[0]

    async def generate_many(
        self,
        prompt: str,
        first: bytes,
        *,
        count: int,
        seconds: int,
        prompt_version: str,
        deadline: float,
        negative: str | None = None,
    ) -> list[bytes]:
        return await self._call(
            prompt, first, None, count, seconds, prompt_version, deadline, negative
        )

    async def _call(
        self,
        prompt: str,
        first: bytes,
        last: bytes | None,
        count: int,
        seconds: int,
        prompt_version: str,
        deadline: float,
        negative: str | None,
    ) -> list[bytes]:
        began = time.monotonic()
        limit = began + _remaining(deadline, self._timeout)
        try:
            clips = await self._generate(prompt, first, last, count, seconds, limit, negative)
        except LlmUnavailable as exc:
            self._record(prompt_version, began, exc.code)
            raise
        self._record(prompt_version, began, None)
        return clips

    def _record(self, version: str, started: float, error: str | None) -> None:
        self._recorder(
            LlmUsage(
                call_type=VIDEO_CALL_TYPE,
                model=self.model,
                prompt_version=version,
                input_tokens=None,  # 초 단위 과금이라 토큰 없음(core 미산정)
                output_tokens=None,
                latency_ms=int((time.monotonic() - started) * 1000),
                success=error is None,
                error_code=error,
            )
        )

    async def _generate(
        self,
        prompt: str,
        first: bytes,
        last: bytes | None,
        count: int,
        seconds: int,
        limit: float,
        negative: str | None,
    ) -> list[bytes]:
        began = time.monotonic()

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
            "sampleCount": count,
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
            videos = [
                v
                for v in (state.get("response") or {}).get("videos") or []
                if v.get("bytesBase64Encoded")
            ]
            if "error" in state or not videos:
                raise LlmUnavailable("LLM_INVALID_OUTPUT", retryable=True)
            logger.info(
                "theme video %ss x%d/%d model=%s in %.0fs",
                seconds,
                len(videos),
                count,
                self.model,
                time.monotonic() - began,
            )
            return [base64.b64decode(v["bytesBase64Encoded"]) for v in videos]
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
        self.counts: list[int] = []  # generate_many 호출마다 후보 수(#779)

    async def generate(
        self,
        prompt: str,
        first: bytes,
        last: bytes | None = None,
        *,
        seconds: int,
        prompt_version: str,
        deadline: float,
        negative: str | None = None,
    ) -> bytes:
        _remaining(deadline, 1e9)
        self.calls.append((prompt, first, last, seconds))
        self.negatives.append(negative)
        return await asyncio.to_thread(color_clip, len(self.calls), seconds)

    async def generate_many(
        self,
        prompt: str,
        first: bytes,
        *,
        count: int,
        seconds: int,
        prompt_version: str,
        deadline: float,
        negative: str | None = None,
    ) -> list[bytes]:
        """후보 count개를 generate로 하나씩(calls에 후보마다 1건, 시험이 generate를 바꿔 끼우면
        후보에도 그대로 적용, #779). counts에는 호출마다 후보 수."""
        self.counts.append(count)
        return [
            await self.generate(
                prompt,
                first,
                seconds=seconds,
                prompt_version=prompt_version,
                deadline=deadline,
                negative=negative,
            )
            for _ in range(count)
        ]


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
    확대는 원근 필터(perspective)로 원본 위 네 점을 픽셀 아래 단위로 옮겨 보간한다. 예전
    zoompan은 자를 위치를 정수 픽셀로 반올림해 그림 전체가 1초에 6번 약 1px씩 앞뒤로 튀었음
    (#779 실측 2026-11-18: 프레임 사이 가운데 이동 +0.2·+0.1·+0.1·-0.4px(640px 기준) 되풀이 → 0).
    """
    width, height = size
    frames = max(1, round(seconds * 24))
    edge = f"(1-1/(1+{STILL_ZOOM - 1:.3f}*on/{frames}))/2"  # 가장자리에서 잘라 낼 비율
    left, top, right, bottom = f"W*{edge}", f"H*{edge}", f"W-W*{edge}", f"H-H*{edge}"
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.img", Path(tmp) / "c.mp4"
        src.write_bytes(image)
        _ffmpeg(
            [
                "-loop",
                "1",
                "-framerate",
                "24",
                "-i",
                str(src),
                "-vf",
                f"scale={width}:{height}:flags=lanczos,perspective="
                f"x0='{left}':y0='{top}':x1='{right}':y1='{top}':"
                f"x2='{left}':y2='{bottom}':x3='{right}':y3='{bottom}':"
                "interpolation=cubic:eval=frame",
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


FACE_FADE = 0.3  # 표정 그림 두 장 컷의 녹아드는 시간(초). 0.8초는 두 입이 겹쳐 보였음(#779 비교)
FACE_SWITCH = 0.4  # 컷 길이의 이 비율에서 끝 표정으로 넘어가기 시작


def two_face_clip(first: bytes, second: bytes, seconds: float, size: tuple[int, int]) -> bytes:
    """표정 그림 두 장 컷(#779 사용자 결정 2026-11-20 A안): 첫 그림 → FACE_FADE초 녹아듦 → 끝 그림,
    전체를 가운데로 천천히 확대(still_clip과 같은 원근 필터, 24fps·yuv420p, size 크기)."""
    width, height = size
    frames = max(1, round(seconds * 24))
    edge = f"(1-1/(1+{STILL_ZOOM - 1:.3f}*on/{frames}))/2"
    left, top, right, bottom = f"W*{edge}", f"H*{edge}", f"W-W*{edge}", f"H-H*{edge}"
    switch = round(seconds * FACE_SWITCH, 3)
    with tempfile.TemporaryDirectory() as tmp:
        a, b, out = Path(tmp) / "a.img", Path(tmp) / "b.img", Path(tmp) / "c.mp4"
        a.write_bytes(first)
        b.write_bytes(second)
        fit = f"scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p"
        _ffmpeg(
            [
                *("-loop", "1", "-framerate", "24", "-t", str(seconds), "-i", str(a)),
                *("-loop", "1", "-framerate", "24", "-t", str(seconds), "-i", str(b)),
                "-filter_complex",
                f"[0]{fit}[a];[1]{fit}[b];"
                f"[a][b]xfade=transition=fade:duration={FACE_FADE}:offset={switch}[x];"
                f"[x]perspective=x0='{left}':y0='{top}':x1='{right}':y1='{top}':"
                f"x2='{left}':y2='{bottom}':x3='{right}':y3='{bottom}':"
                "interpolation=cubic:eval=frame[v]",
                *("-map", "[v]", "-frames:v", str(frames)),
                *("-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)),
            ]
        )
        return out.read_bytes()


# 달리기 합성 컷(#779 사용자 결정 2026-11-20 ②안, 시제품 2026-11-21 기준안)
RUN_KEY = "0x00FF00"  # 자세 그림의 초록 배경(prompts.RUN_GREEN)
RUN_KEY_SIMILARITY, RUN_KEY_BLEND = 0.18, 0.08  # 올리브 모자·연두 조끼는 남고 배경만 지워졌음
RUN_STEP_FRAMES = 4  # 이 프레임마다 왼발·오른발 자세를 바꿈(24fps에서 약 0.17초)
RUN_HEIGHT = 0.62  # 뭉치 키(화면 높이 비율)
RUN_BOTTOM = 0.06  # 화면 아래 여백(화면 높이 비율)
RUN_BOUNCE = 6 / 720  # 걸음마다 통통 튀는 높이(화면 높이 비율, 720p에서 6px)
RUN_ZOOM = 1.4  # 배경 처음 배율 → 1.0으로 물러남. 옆으로 흘리면 정면 뭉치가 미끄러져 보였음
RUN_FOCUS_Y = 0.7  # 확대한 배경에서 자를 세로 위치(길이 있는 아래쪽)


def run_clip(road: bytes, steps: Sequence[bytes], seconds: float, size: tuple[int, int]) -> bytes:
    """달리기 합성 컷: 길 배경을 RUN_ZOOM배에서 1배로 천천히 물리고(화면 쪽으로 달려옴), 초록을 지운
    자세 그림(왼발·오른발, 하나면 그 하나)을 화면 가운데 아래에 RUN_STEP_FRAMES마다 번갈아 겹쳐
    걸음마다 살짝 통통 튀게 함(24fps·yuv420p, size 크기). Veo를 쓰지 않음."""
    if not steps:
        raise ValueError("달리기 자세 그림 없음")
    width, height = size
    frames = max(1, round(seconds * 24))
    a, b = steps[0], steps[-1]
    tall = int(height * RUN_HEIGHT)
    zoom = f"({RUN_ZOOM}-{RUN_ZOOM - 1:.3f}*t/{seconds})"
    wide = 2 * round(tall * 16 / 9 / 2)  # 두 자세를 같은 크기로(blend는 크기가 같아야 함)
    key = f"chromakey={RUN_KEY}:{RUN_KEY_SIMILARITY}:{RUN_KEY_BLEND},scale={wide}:{tall}"
    bounce = f"{height * RUN_BOUNCE:.2f}*abs(sin(PI*t*{24 / RUN_STEP_FRAMES / 2}))"
    with tempfile.TemporaryDirectory() as tmp:
        bg, pa, pb, out = (Path(tmp) / x for x in ("bg.img", "a.img", "b.img", "c.mp4"))
        bg.write_bytes(road)
        pa.write_bytes(a)
        pb.write_bytes(b)
        loop = ("-loop", "1", "-framerate", "24", "-t", str(seconds), "-i")
        _ffmpeg(
            [
                *loop,
                str(bg),
                *loop,
                str(pa),
                *loop,
                str(pb),
                "-filter_complex",
                f"[0]scale=w='trunc({width}*{zoom}/2)*2':h='trunc({height}*{zoom}/2)*2':"
                f"eval=frame,crop={width}:{height}:(iw-{width})/2:(ih-{height})*{RUN_FOCUS_Y},"
                "setsar=1[bg];"
                f"[1]{key}[ka];[2]{key}[kb];"
                f"[ka][kb]blend=all_expr='if(lt(mod(floor(N/{RUN_STEP_FRAMES}),2),1),A,B)'[run];"
                f"[bg][run]overlay=x=(W-w)/2:y=H-h-{int(height * RUN_BOTTOM)}-{bounce},"
                "format=yuv420p[v]",
                *("-map", "[v]", "-frames:v", str(frames)),
                *("-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)),
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
    """그림은 버킷이 있어야, 영상은 켜져 있고 프로젝트·Google 자격 증명이 있어야 만든다.

    없으면 None(건너뜀). 영상이 켜져 있는데 자격 증명을 못 찾으면 경고를 남긴다.
    """
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
        elif settings.video_project:
            tokens = google_token_source()
            if tokens is None:
                logger.warning("theme video skipped: Google credentials not found")
            else:
                video = VeoVideoClient(
                    project=settings.video_project,
                    location=settings.video_location,
                    model=settings.video_model,
                    tokens=tokens,
                    timeout=settings.theme_video_timeout,
                    recorder=recorder,
                )
    return image, video
