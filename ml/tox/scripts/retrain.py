"""표현 분류 재학습 작업(#729, 에픽 #688): 이어 학습 → 활성 모델과 비교 → 추천 태그 → 자동 등록.

설계는 learning.md 16절 "재학습 자동화", api-spec 4.1.5·5.2.3, 시퀀스 9.1
1. S3 `models/tox-retrain/last.json`의 labelsUntil 뒤 새 라벨 수. 200건 미만이면 종료 코드 0
2. 내보내기 + 공개 학습 데이터(새 라벨의 3배), 최근 라벨 20%는 홀드아웃
3. 활성 tox- 모델에서 train.py로 이어 학습 → threshold(wordlist.py 규칙)·review_threshold 재계산
4. 후보·활성을 같은 세트(꼭 통과 389·APEACH·홀드아웃)·서비스 조건(양자화·글 하나씩·창 8개씩)으로
   평가 → 5. 추천 태그
6. prepare_model_upload.py로 대조 → 파일마다 전체 SHA-256 PUT·HEAD → core 내부 등록 → last.json

활성화는 하지 않는다. 학습 데이터·체크포인트는 임시 폴더에만 두고 끝나면 지운다.
로그에는 단계·건수·버전·오류 종류만 남긴다(원문·점수·학생 ID 없음, NFR-SEC-05).
단계가 실패하면 EXIT_CODES의 코드로 끝나고 last.json은 바꾸지 않는다.

    OMP_NUM_THREADS=2 python scripts/retrain.py
    # 환경 변수: LEARNING_URL CORE_URL INTERNAL_TOKEN(ops 토큰) S3_BUCKET S3_REGION
    #   [S3_ENDPOINT_URL] [S3_BUCKET_OWNER] [TOX_PUBLIC_DATA_PREFIX]
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import random
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field

from eval import GRID, score_texts
from quant import QUANTIZATION, quantize_int8
from train import (
    ARTIFACT_FILES,
    DATA_SOURCES,
    KID_SOURCE,
    KID_SOURCE_NAME,
    binary_metrics,
    check_artifact,
    read_jsonl,
)
from wordlist import pick

TOX = pathlib.Path(__file__).resolve().parents[1]
REPO = TOX.parents[1]
MUST_PASS = TOX / "eval_sets" / "must_pass.json"

# 기준안: learning.md 16절·이슈 #729
MIN_LABELS = 200
PUBLIC_RATIO = 3
HOLDOUT_RATIO = 0.2
EPOCHS = 2  # 1~2에폭 중 검증 F1이 높은 쪽을 train.py가 저장
MAX_APEACH_DROP = 0.01
MAX_REVIEW_RATE = 0.05
MUST_PASS_COUNTS = {"demo": 241, "web": 97, "trap": 51}
MUST_PASS_COUNT = sum(MUST_PASS_COUNTS.values())
MAX_CHARS = 1500  # 내보내기 글 길이(api-spec 4.1.5, 코드포인트)
SEED = 42
THREADS = "2"  # OMP_NUM_THREADS를 주지 않았을 때

SCOPE = "answer-filter"
LAST_KEY = "models/tox-retrain/last.json"
PUBLIC_PREFIX = "datasets/tox-retrain/public-v1/"
PUBLIC_FILES = (
    "train.jsonl",  # K-MHaS·BEEP!만. 아이 말투 문장 없음(NFR-DAT-03, #887)
    "valid.jsonl",
    "apeach.jsonl",  # 평가에만
    "wordlist_flags.json",
    "must_pass.json",  # eval_sets/must_pass.json과 같은 파일
)
KST = dt.timezone(dt.timedelta(hours=9))  # CronJob 시간대(architecture 4.4)
LABELS = {"OFFENSIVE": 1, "CLEAN": 0}
HTTP_TIMEOUT = 30
REGISTER_TIMEOUT = 60  # core 사전 검사 20초 포함
SERVICE_SOURCE = {
    "name": "서비스 표현 검토 라벨(learning 내보내기)",
    "license": "서비스 내부(처리방침 1.2, #732)",
    "use": "학습·홀드아웃(원문 보관 안 함)",
}
# 묶음 train.jsonl의 source(prepare_data.py) → train_info.json에 적는 이름과 건수 칸
PUBLIC_SOURCES = {
    "kmhas": (DATA_SOURCES[0], "publicKmhas"),
    "beep": (DATA_SOURCES[1], "publicBeep"),
}
KID_LINEAGE = (
    "출발 모델 계보에 아이 말투 문장(eval_sets/kid_train.json) 학습이 있음(#887). "
    "이번 학습 데이터에는 없음"
)

EXIT_CODES = {
    "config": 10,
    "last_read": 11,
    "label_count": 12,
    "export": 13,
    "active_model": 14,
    "dataset": 15,
    "train": 16,
    "evaluate": 17,
    "upload": 18,
    "register": 19,
    "last_write": 20,
    "interrupted": 21,
    "unexpected": 22,
}


class Failed(Exception):
    """단계 실패 사유. 로그에 그대로 나가므로 우리가 정한 낱말·건수만 넣는다."""


class StageError(Exception):
    def __init__(self, stage: str, reason: str):
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


class Interrupted(BaseException):
    """SIGTERM(실행 시간 상한). 임시 폴더를 지우고 끝내려고 예외로 바꾼다."""


def log(event: str, **values) -> None:
    print(" ".join(["tox-retrain", event, *(f"{k}={v}" for k, v in values.items())]), flush=True)


def safe_reason(error: Exception) -> str:
    """예외 문장에는 글이 섞일 수 있어 종류와 오류 코드만."""
    if isinstance(error, Failed):
        return str(error)
    response = getattr(error, "response", None)
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    if code and re.fullmatch(r"[A-Za-z0-9]{1,64}", str(code)):
        return f"{type(error).__name__}:{code}"
    return type(error).__name__


@contextlib.contextmanager
def stage(name: str):
    started = time.monotonic()
    try:
        yield
    except Exception as error:
        raise StageError(name, safe_reason(error)) from None
    log("stage_done", stage=name, seconds=round(time.monotonic() - started, 1))


@dataclass(frozen=True)
class Config:
    learning_url: str
    core_url: str
    token: str = field(repr=False)
    bucket: str = ""
    region: str = ""
    endpoint: str | None = None
    owner: str | None = None
    public_prefix: str = PUBLIC_PREFIX

    @classmethod
    def from_env(cls, env) -> Config:
        # 보내는 쪽이라 INTERNAL_TOKEN(값은 ops 토큰, architecture 2.2)
        names = ("LEARNING_URL", "CORE_URL", "INTERNAL_TOKEN", "S3_BUCKET", "S3_REGION")
        missing = [name for name in names if not env.get(name, "").strip()]
        if missing:
            raise Failed("missing:" + ",".join(missing))
        prefix = env.get("TOX_PUBLIC_DATA_PREFIX") or PUBLIC_PREFIX
        if not re.fullmatch(r"datasets/([A-Za-z0-9_-][A-Za-z0-9._-]*/)+", prefix):
            raise Failed("invalid:TOX_PUBLIC_DATA_PREFIX")
        return cls(
            *(env[name].strip() for name in names),
            endpoint=env.get("S3_ENDPOINT_URL") or None,
            owner=env.get("S3_BUCKET_OWNER") or None,
            public_prefix=prefix,
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Api:
    """learning·core 내부 호출. 재시도 없음(architecture 1.3), 프록시·리다이렉트를 따르지 않음."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        # 학생 글과 토큰이 다른 곳으로 가지 않게
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def request(self, base: str, path: str, body=None, timeout: int = HTTP_TIMEOUT):
        request = urllib.request.Request(
            base.rstrip("/") + path,
            data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Internal-Token": self.cfg.token,
                "X-User-Role": "SYSTEM",
            },
        )
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.load(error)
            except ValueError:
                return error.code, {}

    def get(self, base: str, path: str, **query):
        query = {k: v for k, v in query.items() if v is not None}
        if query:
            path += "?" + urllib.parse.urlencode(query)
        status, body = self.request(base, path)
        if status != 200:
            raise Failed(f"http_{status}")
        return body


def s3_client(cfg: Config):
    import boto3
    from botocore.config import Config as BotoConfig

    options = {
        "retries": {"total_max_attempts": 1},  # 조건부 PUT을 다시 보내면 412가 됨
        "connect_timeout": 5,
        "read_timeout": 120,
    }
    if cfg.endpoint:
        options["s3"] = {"addressing_style": "path"}
    return boto3.client(
        "s3", endpoint_url=cfg.endpoint, region_name=cfg.region, config=BotoConfig(**options)
    )


def owner_args(cfg: Config) -> dict:
    return {"ExpectedBucketOwner": cfg.owner} if cfg.owner else {}


def parse_time(value) -> dt.datetime:
    try:
        at = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise Failed("invalid_time") from None
    if at.tzinfo is None:
        raise Failed("time_without_offset")
    return at


def read_last(s3, cfg: Config) -> str | None:
    """지난 학습의 labelsUntil. 없을 때만 처음부터, 읽지 못하면 실패."""
    try:
        body = s3.get_object(Bucket=cfg.bucket, Key=LAST_KEY, **owner_args(cfg))["Body"].read()
    except Exception as error:
        response = getattr(error, "response", None)
        if isinstance(response, dict) and response.get("Error", {}).get("Code") == "NoSuchKey":
            return None
        raise
    last = json.loads(body)
    if not isinstance(last, dict) or set(last) != {"labelsUntil", "version"}:
        raise Failed("invalid_last")
    parse_time(last["labelsUntil"])
    return last["labelsUntil"]


def parse_count(body) -> tuple[int, str | None]:
    if not isinstance(body, dict) or set(body) != {"count", "latestLabeledAt"}:
        raise Failed("invalid_count")
    count, latest = body["count"], body["latestLabeledAt"]
    if type(count) is not int or count < 0:
        raise Failed("invalid_count")
    if count:
        parse_time(latest)
    return count, latest


def enough_labels(count: int) -> bool:
    return count >= MIN_LABELS


def parse_export(body) -> list[dict]:
    """api-spec 4.1.5 `{items:[{text, label}]}`. 다른 칸(ID 등)이 오면 쓰지 않고 실패."""
    if not isinstance(body, dict) or set(body) != {"items"} or not isinstance(body["items"], list):
        raise Failed("invalid_export")
    rows = []
    for item in body["items"]:
        if not isinstance(item, dict) or set(item) != {"text", "label"}:
            raise Failed("invalid_export_item")
        text, label = item["text"], item["label"]
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
            raise Failed("invalid_export_text")
        if not isinstance(label, str) or label not in LABELS:
            raise Failed("invalid_export_label")
        rows.append({"text": text, "label": LABELS[label]})
    return rows


def split_labels(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """labeled_at 순으로 온 라벨의 뒤 20%가 홀드아웃."""
    held = math.ceil(len(rows) * HOLDOUT_RATIO)
    return rows[: len(rows) - held], rows[len(rows) - held :]


@dataclass
class Dataset:
    train: list[dict]
    valid: list[dict]
    apeach: list[dict]
    holdout: list[dict]
    flags: list[int]
    must_pass: list[str]
    counts: dict


def load_must_pass(path: pathlib.Path) -> list[str]:
    """public-v1 묶음의 고정본. 이미지에 든 고정본과 다르면 평가 세트가 바뀐 것이라 멈춘다."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if {key: len(doc[key]) for key in MUST_PASS_COUNTS} != MUST_PASS_COUNTS:
        raise Failed("must_pass_count")
    if doc != json.loads(MUST_PASS.read_text(encoding="utf-8")):
        raise Failed("must_pass_changed")
    return [text for key in MUST_PASS_COUNTS for text in doc[key]]


def build_dataset(labels: list[dict], public: dict, until: str, seed: int = SEED) -> Dataset:
    """평가에 쓰는 글은 학습에서 빼고(NFR-AIQ-05) 공개 데이터를 새 라벨의 3배 섞는다."""
    if any(row.get("source") == KID_SOURCE_NAME for row in public["train"]):
        raise Failed("generated_text_in_public_data")  # NFR-DAT-03, #887
    if any(row.get("source") not in PUBLIC_SOURCES for row in public["train"]):
        raise Failed("unknown_public_source")
    recent_train, holdout = split_labels(labels)
    evaluated = {row["text"].strip() for row in holdout + public["valid"] + public["apeach"]}
    evaluated |= {text.strip() for text in public["mustPass"]}
    service = [row for row in recent_train if row["text"].strip() not in evaluated]
    pool = [row for row in public["train"] if row["text"].strip() not in evaluated]
    wanted = len(labels) * PUBLIC_RATIO
    if len(pool) < wanted:
        raise Failed("public_data_too_small")
    # 같은 범위면 같은 표본, 주마다는 다른 표본
    mixed = random.Random(f"{seed}:{until}").sample(pool, wanted)
    rows = [{"text": row["text"], "label": row["label"]} for row in service + mixed]
    counts = {
        "labels": len(labels),
        "labelsOffensive": sum(row["label"] for row in labels),
        "serviceTrain": len(service),
        "holdout": len(holdout),
        "holdoutOffensive": sum(row["label"] for row in holdout),
        "publicTrain": len(mixed),
        **{key: 0 for _, key in PUBLIC_SOURCES.values()},
        **Counter(PUBLIC_SOURCES[row["source"]][1] for row in mixed),
        "train": len(rows),
    }
    return Dataset(
        rows,
        public["valid"],
        public["apeach"],
        holdout,
        public["flags"],
        public["mustPass"],
        counts,
    )


def sha256_file(path: pathlib.Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write_jsonl(path: pathlib.Path, rows: list[dict]) -> str:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return sha256_file(path)


def download(s3, cfg: Config, key: str, path: pathlib.Path) -> None:
    response = s3.get_object(Bucket=cfg.bucket, Key=key, **owner_args(cfg))
    with path.open("wb") as f:
        while chunk := response["Body"].read(1024 * 1024):
            f.write(chunk)


def load_public(s3, cfg: Config, folder: pathlib.Path) -> tuple[dict, str]:
    """비공개 경로의 공개 데이터. manifest의 SHA-256과 다르면 쓰지 않는다."""
    folder.mkdir()
    manifest_path = folder / "manifest.json"
    download(s3, cfg, cfg.public_prefix + "manifest.json", manifest_path)
    listed = {x["file"]: x for x in json.loads(manifest_path.read_text(encoding="utf-8"))["files"]}
    if set(listed) != set(PUBLIC_FILES):
        raise Failed("invalid_public_manifest")
    for name in PUBLIC_FILES:
        path = folder / name
        download(s3, cfg, cfg.public_prefix + name, path)
        if sha256_file(path) != listed[name]["sha256"]:
            raise Failed(f"public_hash_mismatch:{name}")
    public = {key: read_jsonl(folder / f"{key}.jsonl") for key in ("train", "valid", "apeach")}
    flags = json.loads((folder / "wordlist_flags.json").read_text(encoding="utf-8"))["valid"]
    if len(flags) != len(public["valid"]) or set(flags) - {0, 1}:
        raise Failed("invalid_wordlist_flags")
    public["flags"] = flags
    public["mustPass"] = load_must_pass(folder / "must_pass.json")
    return public, sha256_file(manifest_path)


def find_active(body, bucket: str) -> dict:
    """활성 tox- 모델 하나와 S3 경로. 없거나 2개 이상이면 어느 쪽에서 이어 배울지 정하지 않는다."""
    found = [
        item
        for item in body["items"]
        if item["kind"] == "MODEL" and item["name"].startswith("tox-") and SCOPE in item["scopes"]
    ]
    if len(found) != 1:
        raise Failed(f"active_models:{len(found)}")
    uri, head = found[0].get("artifactUri") or "", f"s3://{bucket}/"
    prefix = uri.removeprefix(head)
    parts = prefix.split("/")[:-1]
    if (
        not uri.startswith(head)
        or not prefix.startswith("models/")
        or not prefix.endswith("/")
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise Failed("invalid_active_uri")
    return {**found[0], "prefix": prefix}


def download_model(s3, cfg: Config, prefix: str, folder: pathlib.Path) -> dict:
    folder.mkdir()
    for name in ARTIFACT_FILES:
        download(s3, cfg, prefix + name, folder / name)
    if check_artifact(folder):
        raise Failed("invalid_active_artifact")
    info = json.loads((folder / "train_info.json").read_text(encoding="utf-8"))
    if info.get("positiveLabel", 1) != 1:  # train.py·eval.py는 1 = 막을 글
        raise Failed("unsupported_positive_label")
    if info.get("quantization", "none") not in ("none", QUANTIZATION):
        raise Failed("unsupported_quantization")
    return info


def child_env(env) -> dict:
    """train.py에는 토큰·AWS 자격 증명을 넘기지 않는다."""
    child = {
        key: value for key, value in env.items() if not key.startswith(("AWS_", "INTERNAL_TOKEN"))
    }
    child.setdefault("OMP_NUM_THREADS", THREADS)
    child.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    return child


def fit(parent: pathlib.Path, info: dict, data: pathlib.Path, out: pathlib.Path) -> None:
    command = [
        sys.executable,
        str(pathlib.Path(__file__).with_name("train.py")),
        "--data",
        str(data),
        "--out",
        str(out),
        "--model",
        str(parent),
        "--max-length",
        str(info["max_length"]),
        "--epochs",
        str(EPOCHS),
        "--seed",
        str(SEED),
    ]
    # train.py 출력에는 에폭별 점수가, 오류에는 글이 섞일 수 있어 남기지 않는다
    result = subprocess.run(
        command, env=child_env(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    if result.returncode:
        raise Failed(f"train_exit:{result.returncode}")


def score_sets(folder: pathlib.Path, info: dict, sets: dict[str, list[str]]) -> dict:
    """scoring 로더와 같은 방식(quant.py, eval.py score_texts)으로 글별 확률."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(folder, local_files_only=True)
    int8 = info.get("quantization", "none") == QUANTIZATION
    if int8:
        model = quantize_int8(model)
    return {
        name: score_texts(
            model, tokenizer, texts, info["max_length"], info["stride"], "cpu", per_text=int8
        )
        for name, texts in sets.items()
    }


def pick_review_threshold(
    probs: list[float], labels: list[int], threshold: float
) -> tuple[float | None, float]:
    """검증 정상 글 중 경계 구간[review, threshold) 비율이 5% 이하인 가장 낮은 값과 그 비율."""
    normal = [p for p, y in zip(probs, labels, strict=True) if y == 0]
    if not normal:
        raise Failed("no_normal_validation")
    for review in (value for value in GRID if value < threshold):
        rate = sum(1 for p in normal if review <= p < threshold) / len(normal)
        if rate <= MAX_REVIEW_RATE:
            return review, rate
    return None, 0.0


def recommend(
    must_pass_flagged: int,
    holdout_f1: float,
    active_holdout_f1: float,
    apeach_f1: float,
    active_apeach_f1: float,
) -> tuple[str, list[str]]:
    """기준안 세 조건을 모두 넘으면 추천, 아니면 걸린 조건. 참고 정보라 등록은 막지 않는다."""
    failed = []
    if must_pass_flagged:
        failed.append(f"꼭 통과할 글 {must_pass_flagged}개를 막음(기준 0개)")
    if holdout_f1 <= active_holdout_f1:
        failed.append(f"홀드아웃 F1 {holdout_f1:.4f}가 활성 {active_holdout_f1:.4f}보다 높지 않음")
    drop = round(active_apeach_f1 - apeach_f1, 6)  # 1%p 경계의 부동소수점 오차
    if drop > MAX_APEACH_DROP:
        failed.append(f"APEACH F1 하락 {drop * 100:.2f}%p(기준 1%p 이하)")
    if failed:
        return "NOT_RECOMMENDED", failed
    return "RECOMMENDED", [
        "꼭 통과할 글 오탐 0개",
        f"홀드아웃 F1 {holdout_f1:.4f}가 활성 {active_holdout_f1:.4f}보다 높음",
        f"APEACH F1 {apeach_f1:.4f}(활성 {active_apeach_f1:.4f}), 하락 1%p 이하",
    ]


@dataclass
class Comparison:
    threshold: float
    review_threshold: float | None
    tag: str
    reasons: list[str]
    metrics: dict[str, float]


def compare(
    candidate: pathlib.Path, parent: pathlib.Path, parent_info: dict, data: Dataset
) -> Comparison:
    info = json.loads((candidate / "train_info.json").read_text(encoding="utf-8"))
    for key in ("max_length", "stride"):
        info[key] = parent_info[key]
    info["quantization"] = parent_info.get("quantization", "none")

    rows = {"apeach": data.apeach, "holdout": data.holdout}
    texts = {name: [row["text"] for row in part] for name, part in rows.items()}
    texts["mustPass"] = data.must_pass
    new = score_sets(candidate, info, {**texts, "valid": [row["text"] for row in data.valid]})
    old = score_sets(parent, parent_info, texts)

    valid_labels = [row["label"] for row in data.valid]
    threshold, chosen = pick(new["valid"], valid_labels, data.flags, max(new["mustPass"]))
    if threshold is None:
        raise Failed("no_threshold")
    review, review_rate = pick_review_threshold(new["valid"], valid_labels, threshold)

    metrics = {key: float(value) for key, value in data.counts.items()}
    metrics.update(
        candidateThreshold=threshold,
        activeThreshold=parent_info["threshold"],
        validReviewRate=round(review_rate, 4),
        validF1=chosen["model"]["f1"],
        validExtraFalsePositiveRate=chosen["extraFalsePositiveRate"],
        mustPassCount=float(len(data.must_pass)),
    )
    if review is not None:
        metrics["candidateReviewThreshold"] = review
    for side, probs, cut in (
        ("candidate", new, threshold),
        ("active", old, parent_info["threshold"]),
    ):
        metrics[f"{side}MustPassFlagged"] = float(sum(p >= cut for p in probs["mustPass"]))
        for name, label in (("holdout", "Holdout"), ("apeach", "Apeach")):
            result = binary_metrics(probs[name], [row["label"] for row in rows[name]], cut)
            for key in ("precision", "recall", "f1"):
                metrics[f"{side}{label}{key.capitalize()}"] = result[key]
    tag, reasons = recommend(
        int(metrics["candidateMustPassFlagged"]),
        metrics["candidateHoldoutF1"],
        metrics["activeHoldoutF1"],
        metrics["candidateApeachF1"],
        metrics["activeApeachF1"],
    )
    return Comparison(threshold, review, tag, reasons, metrics)


def training_data(counts: dict, labels_sha256: str) -> list[dict]:
    """이번 학습에 쓴 자료만. 출발 모델이 배운 자료는 이어받지 않는다."""
    public = [
        {**source, "use": "학습·검증", "train": counts[key]}
        for source, key in PUBLIC_SOURCES.values()
    ]
    service = {
        **SERVICE_SOURCE,
        "labels": counts["labels"],
        "offensive": counts["labelsOffensive"],
        "train": counts["serviceTrain"],
        "holdout": counts["holdout"],
        "sha256": labels_sha256,
    }
    return [*public, service]


def has_kid_lineage(parent_info: dict) -> bool:
    """출발 모델이나 그 앞 세대가 아이 말투 문장으로 배웠는지."""
    return bool(
        parent_info.get("sizes", {}).get("kidWritten")
        or parent_info.get("initFrom", {}).get("kidWrittenLineage")
        or any(x.get("name") == KID_SOURCE[0]["name"] for x in parent_info.get("data", []))
    )


def finish_info(
    folder: pathlib.Path,
    parent_info: dict,
    active: dict,
    result: Comparison,
    counts: dict,
    hashes: dict,
    day: str,
) -> None:
    """train.py가 쓴 train_info.json에 다시 계산한 임계값과 이번 학습 자료·내력을 넣는다."""
    path = folder / "train_info.json"
    info = json.loads(path.read_text(encoding="utf-8"))
    info.update(
        threshold=result.threshold,
        thresholdSource=f"retrain.py {day}: wordlist.py 규칙, 꼭 통과할 글 {MUST_PASS_COUNT}개",
        quantization=parent_info.get("quantization", "none"),
        max_length=parent_info["max_length"],
        stride=parent_info["stride"],
    )
    info.pop("review_threshold", None)
    if result.review_threshold is not None:
        info["review_threshold"] = result.review_threshold
    info["data"] = training_data(counts, hashes["labels"])
    info["dataSha256"] = hashes
    info["sizes"] = {**info.get("sizes", {}), **counts}
    info["initFrom"] = {
        "model": f"{active['name']}:{active['version']}",
        "trainedAt": parent_info.get("trainedAt"),
    }
    if has_kid_lineage(parent_info):
        info["initFrom"]["kidWrittenLineage"] = KID_LINEAGE
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    if check_artifact(folder):
        raise Failed("invalid_candidate_artifact")


def put_verified(s3, cfg: Config, key: str, source: pathlib.Path, **args) -> None:
    """scoring.md 6.3: 단일 PUT(전체 SHA-256) 뒤 HEAD로 FULL_OBJECT·해시·크기 확인."""
    checksum = base64.b64encode(bytes.fromhex(sha256_file(source))).decode("ascii")
    with source.open("rb") as body:
        put = s3.put_object(
            Bucket=cfg.bucket,
            Key=key,
            Body=body,
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=checksum,
            ContentType="application/json" if key.endswith(".json") else "application/octet-stream",
            **owner_args(cfg),
            **args,
        )
    head = s3.head_object(Bucket=cfg.bucket, Key=key, ChecksumMode="ENABLED", **owner_args(cfg))
    if (
        put.get("ChecksumSHA256") != checksum
        or head.get("ChecksumSHA256") != checksum
        or head.get("ChecksumType") != "FULL_OBJECT"
        or head.get("ContentLength") != source.stat().st_size
    ):
        raise Failed(f"checksum_mismatch:{key.rsplit('/', 1)[-1]}")


def upload(s3, cfg: Config, name: str, version: str, folder: pathlib.Path) -> tuple[str, list]:
    """한 파일이라도 확인이 안 되면 멈춘다. 올라간 객체는 지우지 않는다(scoring.md 6.3)."""
    if str(REPO / "scripts") not in sys.path:
        sys.path.append(str(REPO / "scripts"))
    from prepare_model_upload import prepare

    uri = f"s3://{cfg.bucket}/models/{name}/{version}/"
    files = [
        {
            "file": file,
            "bytes": (folder / file).stat().st_size,
            "sha256": sha256_file(folder / file),
        }
        for file in ARTIFACT_FILES
    ]
    request = {"name": name, "version": version, "artifactUri": uri, "files": files}
    for item in prepare(request, folder, cfg.bucket)["files"]:
        source = pathlib.Path(item["path"])
        put_verified(s3, cfg, item["key"], source, IfNoneMatch="*")
    return uri, files


def registration_body(
    active: dict,
    version: str,
    uri: str,
    files: list,
    until: str,
    result: Comparison,
    counts: dict,
    hashes: dict,
) -> dict:
    """evaluation에 지표·추천·건수·해시(api-spec 5.2.3). 글·학생 ID는 넣지 않는다."""
    baseline = f"{active['name']}:{active['version']}"
    evidence = {
        "datasetId": (
            f"tox-retrain train-sha256:{hashes['train']} holdout-sha256:{hashes['holdout']} "
            f"public-manifest-sha256:{hashes['public']}"
        ),
        "datasetVersion": until,
        "baselineVersion": baseline,
        "comparisonReport": (
            f"활성 {baseline}과 같은 세트 비교: 꼭 통과할 글 {MUST_PASS_COUNT}개·APEACH·"
            f"홀드아웃 {counts['holdout']}건. 결과 {result.tag}, 숫자는 recommendation.metrics"
        ),
        "trainingEvaluationSeparation": (
            f"새 라벨 {counts['labels']}건 중 최근 {counts['holdout']}건 홀드아웃, "
            f"학습 {counts['train']}건(서비스 {counts['serviceTrain']}·"
            f"공개 {counts['publicTrain']}). 평가 세트와 같은 글은 학습에서 제외"
        ),
        "quoteAccuracy": "해당 없음(표현 분류 모델)",
        "calculationAccuracy": "해당 없음(표현 분류 모델)",
        "humanReview": "자동 평가만 함. 사람 검토·승인은 활성화 때(NFR-AIQ-05)",
        "evaluatedScopes": [SCOPE],
        "limitations": [
            "추천 태그는 참고 정보이며 활성화 조건이 아님",
            "이어 학습이라 활성 모델의 학습 자료와 한계를 이어받음",
            "홀드아웃은 최근 라벨만이라 표본이 작고, 공개 평가 글은 초등 답과 말투가 다름",
        ],
        "recommendation": {
            "tag": result.tag,
            "comparedTo": baseline,
            "reasons": result.reasons,
            "metrics": result.metrics,
        },
    }
    return {
        "kind": "MODEL",
        "name": active["name"],
        "version": version,
        "artifactUri": uri,
        "evaluation": evidence,
        "registration": {
            "source": "PIPELINE",
            "datasetSha256": hashes["train"],
            "artifactFiles": files,
        },
    }


def register(api, cfg: Config, body: dict) -> bool:
    """새로 등록하면 True, 같은 버전이 이미 있으면(409) False."""
    status, answer = api.request(
        cfg.core_url, "/internal/model-versions", body, timeout=REGISTER_TIMEOUT
    )
    if status == 201 and answer.get("status") == "REGISTERED":
        return True
    code = answer.get("code")
    if status == 409 and code == "MODEL_VERSION_CONFLICT":
        return False
    known = isinstance(code, str) and re.fullmatch(r"[A-Z_]{1,64}", code)
    raise Failed(f"http_{status}" + (f":{code}" if known else ""))


def run(cfg: Config, api, s3, now: dt.datetime) -> None:
    version = now.astimezone(KST).strftime("%Y%m%d-%H%M")  # api-spec 5.2.3
    with stage("last_read"):
        since = read_last(s3, cfg)
    with stage("label_count"):
        path = "/internal/expression-reviews/label-count"
        count, until = parse_count(api.get(cfg.learning_url, path, since=since))
    if not enough_labels(count):
        log("skip", reason="not_enough_labels", count=count, minimum=MIN_LABELS)
        return

    with tempfile.TemporaryDirectory(prefix="tox-retrain-") as temp:
        work = pathlib.Path(temp)
        with stage("export"):
            path = "/internal/expression-reviews/export"
            labels = parse_export(api.get(cfg.learning_url, path, since=since, until=until))
        if not enough_labels(len(labels)):  # 그사이 삭제된 학생 행만큼 줄 수 있음
            log("skip", reason="not_enough_exported", count=len(labels), minimum=MIN_LABELS)
            return
        with stage("active_model"):
            body = api.get(cfg.core_url, "/internal/model-versions/active")
            active = find_active(body, cfg.bucket)
            parent = work / "active"
            parent_info = download_model(s3, cfg, active["prefix"], parent)
        with stage("dataset"):
            public, public_hash = load_public(s3, cfg, work / "public")
            data = build_dataset(labels, public, until)
            folder = work / "data"
            folder.mkdir()
            hashes = {
                "labels": write_jsonl(folder / "labels.jsonl", labels),
                "train": write_jsonl(folder / "train.jsonl", data.train),
                "holdout": write_jsonl(folder / "holdout.jsonl", data.holdout),
                "public": public_hash,
            }
            write_jsonl(folder / "valid.jsonl", data.valid)
        log("dataset", **data.counts)
        candidate = work / "candidate"
        with stage("train"):
            fit(parent, parent_info, folder, candidate)
        with stage("evaluate"):
            result = compare(candidate, parent, parent_info, data)
            day = now.astimezone(KST).date().isoformat()
            finish_info(candidate, parent_info, active, result, data.counts, hashes, day)
        with stage("upload"):
            uri, files = upload(s3, cfg, active["name"], version, candidate)
        with stage("register"):
            body = registration_body(
                active, version, uri, files, until, result, data.counts, hashes
            )
            created = register(api, cfg, body)
        if not created:
            log("already_registered", name=active["name"], version=version)
            return
        log("registered", name=active["name"], version=version, tag=result.tag)
        with stage("last_write"):
            last = work / "last.json"
            last.write_text(json.dumps({"labelsUntil": until, "version": version}), "utf-8")
            put_verified(s3, cfg, LAST_KEY, last)


def _interrupt(*_):
    raise Interrupted


def main(env=None, api=None, s3=None, now: dt.datetime | None = None) -> int:
    os.environ.setdefault("OMP_NUM_THREADS", THREADS)  # torch를 불러오기 전에
    previous = signal.signal(signal.SIGTERM, _interrupt)
    try:
        with stage("config"):
            cfg = Config.from_env(os.environ if env is None else env)
            api = api or Api(cfg)
            s3 = s3 or s3_client(cfg)
        run(cfg, api, s3, now or dt.datetime.now(dt.timezone.utc))
    except StageError as error:
        code = EXIT_CODES[error.stage]
        log("failed", stage=error.stage, reason=error.reason, exit=code)
        return code
    except (Interrupted, KeyboardInterrupt):
        log("failed", stage="interrupted", exit=EXIT_CODES["interrupted"])
        return EXIT_CODES["interrupted"]
    except Exception as error:
        code = EXIT_CODES["unexpected"]
        log("failed", stage="unexpected", reason=type(error).__name__, exit=code)
        return code
    finally:
        signal.signal(signal.SIGTERM, previous)
    log("finished", exit=0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
