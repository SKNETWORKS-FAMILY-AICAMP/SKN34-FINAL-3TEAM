"""재학습 작업(#729) 시험. torch·boto3·실제 데이터 없이 가짜 learning·core·S3로 흐름까지."""

import base64
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import urllib.parse

import pytest
import retrain as R
import train as T

UNTIL = "2026-11-22T15:00:00.123456Z"
NOW = dt.datetime(2026, 11, 22, 18, 0, tzinfo=dt.timezone.utc)  # KST 11/23 03:00
VERSION = "20261123-0300"
BUCKET = "test-models"
MODEL = "tox-koelectra-small"
ACTIVE_PREFIX = f"models/{MODEL}/1.0-1119/"
NEW_PREFIX = f"models/{MODEL}/{VERSION}/"
PUBLIC = R.PUBLIC_PREFIX
SECRET_TEXT = "로그에-나오면-안-되는-글"
TOKEN = "test-ops-token-not-secret"
ENV = {
    "LEARNING_URL": "http://learning",
    "CORE_URL": "http://core",
    "INTERNAL_TOKEN": TOKEN,
    "S3_BUCKET": BUCKET,
    "S3_REGION": "ap-northeast-2",
}


def jsonl(rows):
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()


class S3Error(Exception):
    def __init__(self, code):
        super().__init__(SECRET_TEXT)  # 예외 문장은 로그에 남기지 않는지
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.puts = []
        self.fail_put = None  # 이 파일 이름의 PUT 실패
        self.get_error = None
        self.put_changes = {}
        self.head_changes = {}

    def get_object(self, Bucket, Key, **_):
        assert Bucket == BUCKET
        if self.get_error and Key == R.LAST_KEY:
            raise S3Error(self.get_error)
        if Key not in self.objects:
            raise S3Error("NoSuchKey")
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ChecksumSHA256, **args):
        assert Bucket == BUCKET and args["ChecksumAlgorithm"] == "SHA256"
        if self.fail_put and Key.endswith(self.fail_put):
            raise S3Error("BadDigest")
        data = Body.read()
        assert ChecksumSHA256 == base64.b64encode(hashlib.sha256(data).digest()).decode()
        if args.get("IfNoneMatch") == "*" and Key in self.objects:
            raise S3Error("PreconditionFailed")
        self.objects[Key] = data
        self.puts.append((Key, args))
        return {"ChecksumSHA256": ChecksumSHA256, **self.put_changes}

    def head_object(self, Bucket, Key, ChecksumMode, **_):
        assert ChecksumMode == "ENABLED"
        data = self.objects[Key]
        return {
            "ChecksumSHA256": base64.b64encode(hashlib.sha256(data).digest()).decode(),
            "ChecksumType": "FULL_OBJECT",
            "ContentLength": len(data),
            **self.head_changes,
        }


def problem(status, code):
    """core-service.yaml Problem."""
    return status, {
        "type": "about:blank",
        "title": code,
        "status": status,
        "code": code,
        "detail": None,
        "traceId": "0" * 32,
    }


class FakeApi:
    """응답 칸은 learning-service.yaml·core-service.yaml과 같게(#912와 같은 기준)."""

    def __init__(self, count=200):
        self.count = count
        self.items = [
            {"text": f"{SECRET_TEXT} {i}", "label": "OFFENSIVE" if i % 2 else "CLEAN"}
            for i in range(count)
        ]
        self.register_answer = None  # 주면 그 응답, 없으면 201 ModelVersion
        self.calls = []
        self.failing = None  # 이 경로는 503

    def get(self, base, path, **query):
        self.calls.append((path, query))
        if path == self.failing:
            raise R.Failed("http_503")
        if path.endswith("/label-count"):
            return {"count": self.count, "latestLabeledAt": UNTIL if self.count else None}
        if path.endswith("/export"):
            return {"items": self.items}
        assert path == "/internal/model-versions/active"
        return {
            "items": [
                {
                    "id": "00000000-0000-4000-8000-000000000001",
                    "kind": "MODEL",
                    "name": MODEL,
                    "version": "1.0-1119",
                    "refId": None,
                    "artifactUri": f"s3://{BUCKET}/{ACTIVE_PREFIX}",
                    "scopes": [R.SCOPE],
                    "revision": 1,
                    "activatedAt": "2026-11-19T03:00:00Z",
                }
            ]
        }

    def request(self, base, path, body=None, timeout=None):
        self.calls.append((path, body))
        assert path == "/internal/model-versions"
        if self.register_answer:
            return self.register_answer
        return 201, {
            "id": "00000000-0000-4000-8000-000000000002",
            **{key: body[key] for key in ("kind", "name", "version", "artifactUri")},
            "refId": None,
            "evalResult": {
                "evidence": body["evaluation"],
                "approval": None,
                "activeScopes": [],
                "revision": 0,
            },
            "status": "REGISTERED",
            "approvedBy": None,
            "activatedAt": None,
            "createdAt": "2026-11-22T18:10:00Z",
        }

    def paths(self):
        return [path for path, _ in self.calls]


def model_files(**info):
    train_info = {
        "max_length": 128,
        "stride": 32,
        "threshold": 0.99,
        "quantization": R.QUANTIZATION,
        "positiveLabel": 1,
        "trainedAt": "2026-11-19T02:57:29+00:00",
        "data": T.DATA_SOURCES + T.KID_SOURCE,  # 지금 서비스 모델(1.0-1119)과 같은 모양
        "sizes": {"train": 88168, "kidWritten": 2073},
        **info,
    }
    return {
        "config.json": json.dumps({"id2label": {"0": "ok", "1": "block"}}).encode(),
        "model.safetensors": b"fake-weights",
        "tokenizer.json": b"{}",
        "tokenizer_config.json": b"{}",
        "train_info.json": json.dumps(train_info).encode(),
    }


def public_files():
    files = {
        "train.jsonl": jsonl(
            {"text": f"공개 학습 {i}", "label": i % 2, "source": "beep" if i % 10 == 0 else "kmhas"}
            for i in range(900)
        ),
        "valid.jsonl": jsonl({"text": f"공개 검증 {i}", "label": i % 2} for i in range(20)),
        "apeach.jsonl": jsonl({"text": f"공개 시험 {i}", "label": i % 2} for i in range(10)),
        "wordlist_flags.json": json.dumps({"valid": [0] * 20}).encode(),
        "must_pass.json": R.MUST_PASS.read_bytes(),
    }
    listed = [
        {"file": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in files.items()
    ]
    return {**files, "manifest.json": json.dumps({"files": listed}).encode()}


@pytest.fixture
def s3():
    fake = FakeS3()
    fake.objects.update({ACTIVE_PREFIX + name: data for name, data in model_files().items()})
    fake.objects.update({PUBLIC + name: data for name, data in public_files().items()})
    return fake


@pytest.fixture
def seen(monkeypatch, tmp_path):
    """학습·추론만 가짜. 나머지(데이터 만들기·임계값·업로드 대조·등록 본문)는 실제 코드."""
    seen = {}
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(R.tempfile, "tempdir", str(temp))
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    seen["temp"] = temp

    def fake_fit(parent, info, data, out):
        seen["work"] = data.parent
        seen["train"] = R.read_jsonl(data / "train.jsonl")
        seen["holdout"] = R.read_jsonl(data / "holdout.jsonl")
        out.mkdir()
        sizes = {"train": len(seen["train"]), "valid": 20}  # train.py가 쓰는 모양
        for name, body in model_files(threshold=0.5, quantization="none", sizes=sizes).items():
            (out / name).write_bytes(body)

    def fake_scores(folder, info, sets):
        seen.setdefault("modes", []).append((folder.name, info["quantization"]))
        if folder.name == "active":
            assert "valid" not in sets
            return {name: [0.1] * len(texts) for name, texts in sets.items()}
        scores = {name: [0.1] * len(texts) for name, texts in sets.items()}
        scores["valid"] = [0.995 if i % 2 else 0.1 for i in range(len(sets["valid"]))]
        scores["holdout"] = [0.995 if i % 2 else 0.1 for i in range(len(sets["holdout"]))]
        return scores

    monkeypatch.setattr(R, "fit", fake_fit)
    monkeypatch.setattr(R, "score_sets", fake_scores)
    return seen


def execute(api, s3):
    return R.main(env=ENV, api=api, s3=s3, now=NOW)


# 추천 규칙


def test_recommended_when_all_rules_pass():
    tag, reasons = R.recommend(0, 0.71, 0.70, 0.50, 0.505)
    assert tag == "RECOMMENDED" and len(reasons) == 3


@pytest.mark.parametrize(
    "values, word",
    [
        ((1, 0.8, 0.7, 0.5, 0.5), "꼭 통과"),
        ((0, 0.7, 0.7, 0.5, 0.5), "홀드아웃"),  # 같으면 추천 아님
        ((0, 0.6, 0.7, 0.5, 0.5), "홀드아웃"),
        ((0, 0.8, 0.7, 0.4899, 0.5), "APEACH"),
    ],
)
def test_not_recommended_names_the_failed_rule(values, word):
    tag, reasons = R.recommend(*values)
    assert tag == "NOT_RECOMMENDED" and len(reasons) == 1 and word in reasons[0]


def test_not_recommended_lists_every_failed_rule():
    assert len(R.recommend(2, 0.1, 0.2, 0.3, 0.5)[1]) == 3


@pytest.mark.parametrize("candidate, active", [(0.50, 0.51), (0.5073, 0.5173), (0.6, 0.5)])
def test_apeach_drop_of_one_point_is_allowed(candidate, active):
    assert R.recommend(0, 0.8, 0.7, candidate, active)[0] == "RECOMMENDED"


# 200·199 판단


@pytest.mark.parametrize("count, enough", [(0, False), (199, False), (200, True), (201, True)])
def test_label_minimum(count, enough):
    assert R.enough_labels(count) is enough


@pytest.mark.parametrize("count", [0, 199])
def test_too_few_labels_exit_zero_without_changes(count, s3, seen, capsys):
    api = FakeApi(count)
    before = dict(s3.objects)
    assert execute(api, s3) == 0
    assert api.paths() == ["/internal/expression-reviews/label-count"]
    assert s3.objects == before and not s3.puts and "work" not in seen
    assert "not_enough_labels" in capsys.readouterr().out


def test_export_shrunk_below_minimum_exits_zero(s3, seen):
    api = FakeApi(200)
    api.items = api.items[:199]
    assert execute(api, s3) == 0
    assert not s3.puts and "work" not in seen


# 내보내기 형식


def test_export_format():
    body = {"items": [{"text": "가", "label": "OFFENSIVE"}, {"text": "나\n다", "label": "CLEAN"}]}
    assert R.parse_export(body) == [{"text": "가", "label": 1}, {"text": "나\n다", "label": 0}]


def test_export_length_counts_code_points():
    text = "\U0001f600" * R.MAX_CHARS
    assert R.parse_export({"items": [{"text": text, "label": "CLEAN"}]})[0]["text"] == text


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"items": {}},
        {"items": [], "total": 0},
        {"items": ["글"]},
        {"items": [{"text": "가"}]},
        {"items": [{"text": "가", "label": "SKIP"}]},
        {"items": [{"text": "가", "label": 1}]},
        {"items": [{"text": "가", "label": ["CLEAN"]}]},
        {"items": [{"text": " ", "label": "CLEAN"}]},
        {"items": [{"text": "가" * 1501, "label": "CLEAN"}]},
        {"items": [{"text": "가", "label": "CLEAN", "studentId": "x"}]},
    ],
)
def test_export_rejects_other_shapes(body):
    with pytest.raises(R.Failed):
        R.parse_export(body)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"count": True, "latestLabeledAt": UNTIL},
        {"count": -1, "latestLabeledAt": None},
        {"count": 200, "latestLabeledAt": None},
        {"count": 200, "latestLabeledAt": "2026-11-22T15:00:00"},
    ],
)
def test_count_rejects_other_shapes(body):
    with pytest.raises(R.Failed):
        R.parse_count(body)


# 학습 데이터


def test_newest_twenty_percent_is_held_out():
    rows = [{"text": str(i), "label": 0} for i in range(200)]
    train, held = R.split_labels(rows)
    assert train == rows[:160] and held == rows[160:]


def test_dataset_mixes_three_times_and_separates_evaluation():
    labels = [{"text": f"라벨 {i}", "label": i % 2} for i in range(10)]
    labels[0] = {"text": "라벨 9", "label": 1}  # 홀드아웃과 같은 글
    public = {
        "train": [
            {"text": text, "label": 0, "source": "kmhas"}
            for text in [f"공개 {i}" for i in range(40)] + ["라벨 8", "검증"]
        ],
        "valid": [{"text": "검증", "label": 0}],
        "apeach": [{"text": "공개 0", "label": 0}],
        "flags": [0],
        "mustPass": ["공개 1"],
    }
    data = R.build_dataset(labels, public, UNTIL)
    texts = {row["text"] for row in data.train}
    assert data.counts["publicTrain"] == 30 and data.counts["serviceTrain"] == 7
    assert not texts & {"라벨 8", "라벨 9", "검증", "공개 0", "공개 1"}
    assert data.train == R.build_dataset(labels, public, UNTIL).train


def test_public_data_must_not_hold_generated_sentences():
    public = {
        "train": [{"text": "가", "label": 0, "source": "kid-written"}],
        "valid": [],
        "apeach": [],
        "flags": [],
        "mustPass": [],
    }
    with pytest.raises(R.Failed, match="generated_text"):
        R.build_dataset([{"text": "나", "label": 0}], public, UNTIL)


@pytest.mark.parametrize("source", [None, "other"])
def test_public_data_is_only_kmhas_and_beep(source):
    public = {
        "train": [{"text": "가", "label": 0, "source": source}],
        "valid": [],
        "apeach": [],
        "flags": [],
        "mustPass": [],
    }
    with pytest.raises(R.Failed, match="unknown_public_source"):
        R.build_dataset([{"text": "나", "label": 0}], public, UNTIL)


def test_must_pass_set_is_fixed_at_389():
    texts = R.load_must_pass(R.MUST_PASS)
    assert len(texts) == 389 and "바보야" not in texts


@pytest.mark.parametrize("change", ["remove", "replace"])
def test_must_pass_bundle_must_equal_fixed_file(change, tmp_path: pathlib.Path):
    doc = json.loads(R.MUST_PASS.read_text(encoding="utf-8"))
    if change == "remove":
        doc["web"].pop()
    else:
        doc["web"][0] = "다른 문장"
    path = tmp_path / "must_pass.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(R.Failed, match="must_pass"):
        R.load_must_pass(path)


# 경계 구간


def test_review_threshold_keeps_five_percent_of_normal():
    probs = [0.001] * 90 + [0.3] * 5 + [0.2] * 5 + [0.9] * 10
    labels = [0] * 100 + [1] * 10
    assert R.pick_review_threshold(probs, labels, 0.95) == (0.21, 0.05)


def test_review_threshold_stays_below_threshold():
    assert R.pick_review_threshold([0.5], [0], 0.01) == (None, 0.0)
    review, rate = R.pick_review_threshold([0.995, 0.1], [0, 0], 0.99)
    assert 0 < review < 0.99 and rate == 0


# 흐름·등록 본문


def test_full_run_registers_and_records_last(s3, seen, capsys):
    api = FakeApi()
    assert execute(api, s3) == 0
    assert len(seen["train"]) == 760 and len(seen["holdout"]) == 40

    body = api.calls[-1][1]
    evidence = body["evaluation"]
    recommendation = evidence["recommendation"]
    assert body["name"] == MODEL and body["version"] == VERSION
    assert body["artifactUri"] == f"s3://{BUCKET}/{NEW_PREFIX}"
    assert evidence["datasetVersion"] == UNTIL and evidence["evaluatedScopes"] == [R.SCOPE]
    assert recommendation["tag"] == "RECOMMENDED"
    assert recommendation["comparedTo"] == f"{MODEL}:1.0-1119"
    assert recommendation["metrics"]["labels"] == 200
    assert recommendation["metrics"]["publicTrain"] == 600
    assert 1 <= len(recommendation["reasons"]) <= 20 and len(recommendation["metrics"]) <= 50
    assert body["registration"]["source"] == "PIPELINE"
    assert body["registration"]["datasetSha256"] in evidence["datasetId"]
    assert len(body["registration"]["artifactFiles"]) == 5
    assert SECRET_TEXT not in json.dumps(body, ensure_ascii=False)

    info = json.loads(s3.objects[NEW_PREFIX + "train_info.json"])
    assert 0 < info["review_threshold"] < info["threshold"] < 1
    assert info["quantization"] == R.QUANTIZATION
    assert info["initFrom"]["model"] == f"{MODEL}:1.0-1119"
    assert seen["modes"] == [("candidate", R.QUANTIZATION), ("active", R.QUANTIZATION)]

    assert [key for key, _ in s3.puts][-1] == R.LAST_KEY
    assert all(args.get("IfNoneMatch") == "*" for _, args in s3.puts[:-1])
    assert json.loads(s3.objects[R.LAST_KEY]) == {"labelsUntil": UNTIL, "version": VERSION}

    out = capsys.readouterr().out
    assert SECRET_TEXT not in out and TOKEN not in out and "f1" not in out.lower()
    assert not any(seen["temp"].iterdir())


def test_label_between_two_count_queries_is_exported(s3, seen):
    """#907 5: count보다 latest가 새로워도 until=latest로 받아 온 글은 모두 쓴다."""
    api = FakeApi(201)
    api.count = 200
    assert execute(api, s3) == 0
    assert api.calls[-1][1]["evaluation"]["recommendation"]["metrics"]["labels"] == 201


def test_next_run_starts_after_labels_until(s3, seen):
    since = "2026-11-15T03:00:00+09:00"
    s3.objects[R.LAST_KEY] = json.dumps({"labelsUntil": since, "version": "x"}).encode()
    api = FakeApi()
    assert execute(api, s3) == 0
    assert api.calls[0][1] == {"since": since}
    assert api.calls[1][1] == {"since": since, "until": UNTIL}


def test_not_recommended_is_still_registered(s3, seen, monkeypatch):
    scores = R.score_sets

    def same_holdout(folder, info, sets):
        result = scores(folder, info, sets)
        result["holdout"] = [0.1] * len(sets["holdout"])
        return result

    monkeypatch.setattr(R, "score_sets", same_holdout)
    api = FakeApi()
    assert execute(api, s3) == 0
    assert api.calls[-1][1]["evaluation"]["recommendation"]["tag"] == "NOT_RECOMMENDED"
    assert R.LAST_KEY in s3.objects


# 새 모델 train_info.json


def uploaded_info(s3):
    return json.loads(s3.objects[NEW_PREFIX + "train_info.json"])


def test_train_info_describes_only_this_training(s3, seen):
    api = FakeApi()
    assert execute(api, s3) == 0
    info = uploaded_info(s3)
    kmhas, beep, service = info["data"]
    assert [x["name"] for x in info["data"]] == [
        "K-MHaS",
        "Korean HateSpeech (BEEP!)",
        R.SERVICE_SOURCE["name"],
    ]
    assert kmhas["use"] == beep["use"] == "학습·검증"  # 시험셋은 쓰지 않음
    assert kmhas["train"] + beep["train"] == 600 and kmhas["train"] and beep["train"]
    assert (service["labels"], service["offensive"]) == (200, 100)
    assert (service["train"], service["holdout"]) == (160, 40)
    rows = [{"text": x["text"], "label": R.LABELS[x["label"]]} for x in api.items]
    assert service["sha256"] == hashlib.sha256(jsonl(rows)).hexdigest()
    assert info["dataSha256"]["labels"] == service["sha256"]
    assert info["dataSha256"]["train"] == api.calls[-1][1]["registration"]["datasetSha256"]
    assert set(info["dataSha256"]) == {"labels", "train", "holdout", "public"}
    assert SECRET_TEXT not in json.dumps(info, ensure_ascii=False)


def test_train_info_does_not_inherit_team_written(s3, seen):
    assert execute(FakeApi(), s3) == 0
    info = uploaded_info(s3)
    assert T.KID_SOURCE[0]["license"] not in json.dumps(info, ensure_ascii=False)
    assert T.KID_SOURCE[0]["name"] not in [x["name"] for x in info["data"]]
    assert "kidWritten" not in info["sizes"]
    assert info["initFrom"]["kidWrittenLineage"] == R.KID_LINEAGE


@pytest.mark.parametrize(
    "parent, lineage",
    [
        ({"sizes": {}, "data": T.DATA_SOURCES}, False),
        ({"sizes": {"kidWritten": 691}, "data": []}, True),
        ({"sizes": {}, "data": T.KID_SOURCE}, True),
        ({"sizes": {}, "data": [], "initFrom": {"kidWrittenLineage": "앞 세대"}}, True),
    ],
)
def test_kid_lineage_follows_generations(parent, lineage, s3, seen):
    s3.objects[ACTIVE_PREFIX + "train_info.json"] = model_files(**parent)["train_info.json"]
    assert execute(FakeApi(), s3) == 0
    info = uploaded_info(s3)
    assert ("kidWrittenLineage" in info["initFrom"]) is lineage
    assert T.KID_SOURCE[0]["license"] not in json.dumps(info, ensure_ascii=False)


# 업로드 실패 시 등록 안 함


def assert_not_registered(api, s3):
    assert "/internal/model-versions" not in api.paths()
    assert R.LAST_KEY not in s3.objects


@pytest.mark.parametrize("name", R.ARTIFACT_FILES)
def test_upload_failure_does_not_register(name, s3, seen, capsys):
    api = FakeApi()
    s3.fail_put = f"{VERSION}/{name}"
    assert execute(api, s3) == R.EXIT_CODES["upload"]
    assert_not_registered(api, s3)
    out = capsys.readouterr().out
    assert "S3Error:BadDigest" in out and SECRET_TEXT not in out
    assert not any(seen["temp"].iterdir())


@pytest.mark.parametrize(
    "where, change",
    [
        ("head_changes", {"ChecksumType": "COMPOSITE"}),
        ("head_changes", {"ChecksumType": None}),
        ("head_changes", {"ChecksumSHA256": "wrong"}),
        ("head_changes", {"ContentLength": 1}),
        ("put_changes", {"ChecksumSHA256": "wrong"}),
    ],
)
def test_upload_checksum_mismatch_does_not_register(where, change, s3, seen):
    api = FakeApi()
    setattr(s3, where, change)
    assert execute(api, s3) == R.EXIT_CODES["upload"]
    assert_not_registered(api, s3)


def test_existing_key_is_not_overwritten(s3, seen):
    api = FakeApi()
    s3.objects[NEW_PREFIX + "config.json"] = b"old"
    assert execute(api, s3) == R.EXIT_CODES["upload"]
    assert s3.objects[NEW_PREFIX + "config.json"] == b"old"
    assert_not_registered(api, s3)


# 단계별 실패


@pytest.mark.parametrize(
    "path, name",
    [
        ("/internal/expression-reviews/label-count", "label_count"),
        ("/internal/expression-reviews/export", "export"),
        ("/internal/model-versions/active", "active_model"),
    ],
)
def test_api_failure_exit_code(path, name, s3, seen):
    api = FakeApi()
    api.failing = path
    assert execute(api, s3) == R.EXIT_CODES[name]
    assert_not_registered(api, s3)
    assert not any(seen["temp"].iterdir())


def test_changed_public_data_is_rejected(s3, seen):
    api = FakeApi()
    s3.objects[PUBLIC + "valid.jsonl"] += b"\n"
    assert execute(api, s3) == R.EXIT_CODES["dataset"]
    assert_not_registered(api, s3)


def test_train_failure_removes_learning_data(s3, seen, monkeypatch, capsys):
    def broken(parent, info, data, out):
        assert (data / "train.jsonl").is_file()
        raise ValueError(SECRET_TEXT)

    monkeypatch.setattr(R, "fit", broken)
    api = FakeApi()
    assert execute(api, s3) == R.EXIT_CODES["train"]
    assert SECRET_TEXT not in capsys.readouterr().out
    assert not any(seen["temp"].iterdir())
    assert_not_registered(api, s3)


def test_interrupt_removes_learning_data(s3, seen, monkeypatch):
    def stopped(*_):
        raise R.Interrupted

    monkeypatch.setattr(R, "fit", stopped)
    assert execute(FakeApi(), s3) == R.EXIT_CODES["interrupted"]
    assert not any(seen["temp"].iterdir())


def test_no_threshold_fails_evaluation(s3, seen, monkeypatch):
    scores = R.score_sets

    def high_must_pass(folder, info, sets):
        result = scores(folder, info, sets)
        result["mustPass"] = [0.999] * len(sets["mustPass"])
        return result

    monkeypatch.setattr(R, "score_sets", high_must_pass)
    api = FakeApi()
    assert execute(api, s3) == R.EXIT_CODES["evaluate"]
    assert_not_registered(api, s3)


@pytest.mark.parametrize(
    "answer",
    [
        problem(422, "MODEL_APPROVAL_REJECTED"),
        problem(502, "MODEL_PREFLIGHT_INVALID_RESPONSE"),
        problem(503, "MODEL_PREFLIGHT_UNAVAILABLE"),
        (201, {}),  # 계약 밖 응답
        problem(409, "OTHER"),
    ],
)
def test_register_failure_keeps_last(answer, s3, seen):
    old = json.dumps({"labelsUntil": "2026-11-01T00:00:00Z", "version": "old"}).encode()
    s3.objects[R.LAST_KEY] = old
    api = FakeApi()
    api.register_answer = answer
    assert execute(api, s3) == R.EXIT_CODES["register"]
    assert s3.objects[R.LAST_KEY] == old


def test_conflict_ends_without_touching_last(s3, seen):
    api = FakeApi()
    api.register_answer = problem(409, "MODEL_VERSION_CONFLICT")
    assert execute(api, s3) == 0
    assert R.LAST_KEY not in s3.objects


def test_unreadable_last_does_not_restart_from_beginning(s3, seen):
    s3.get_error = "AccessDenied"
    api = FakeApi()
    assert execute(api, s3) == R.EXIT_CODES["last_read"]
    assert not api.calls


def test_last_write_failure_is_nonzero(s3, seen):
    s3.fail_put = "last.json"
    assert execute(FakeApi(), s3) == R.EXIT_CODES["last_write"]
    assert R.LAST_KEY not in s3.objects


def test_missing_setting_exit_code():
    assert R.main(env={}) == R.EXIT_CODES["config"]


def test_sender_token_name_is_internal_token():
    receiver_name = {key: value for key, value in ENV.items() if key != "INTERNAL_TOKEN"}
    receiver_name["INTERNAL_TOKEN_OPS"] = TOKEN  # 받는 쪽 이름(architecture 2.2)
    assert R.main(env=receiver_name) == R.EXIT_CODES["config"]


def test_exit_codes_are_distinct_and_nonzero():
    codes = list(R.EXIT_CODES.values())
    assert 0 not in codes and len(set(codes)) == len(codes)


def test_config_hides_token_and_limits_public_prefix():
    assert TOKEN not in repr(R.Config.from_env(ENV))
    for prefix in ("models/x/", "datasets/../models/", "datasets/x"):
        with pytest.raises(R.Failed):
            R.Config.from_env({**ENV, "TOX_PUBLIC_DATA_PREFIX": prefix})


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"artifactUri": f"s3://{BUCKET}/{ACTIVE_PREFIX}"}] * 2,
        [{"artifactUri": f"s3://other/{ACTIVE_PREFIX}"}],
        [{"artifactUri": f"s3://{BUCKET}/datasets/x/"}],
        [{"artifactUri": f"s3://{BUCKET}/models/../x/"}],
    ],
)
def test_active_model_must_be_single_and_in_model_bucket(items):
    base = {"kind": "MODEL", "name": MODEL, "version": "1", "scopes": [R.SCOPE]}
    with pytest.raises(R.Failed):
        R.find_active({"items": [{**base, **item} for item in items]}, BUCKET)


def test_train_process_gets_threads_but_no_secrets():
    env = R.child_env({**ENV, "AWS_SECRET_ACCESS_KEY": "x", "PATH": os.defpath})
    assert "INTERNAL_TOKEN" not in env and "AWS_SECRET_ACCESS_KEY" not in env
    assert env["OMP_NUM_THREADS"] == R.THREADS and env["HF_HUB_OFFLINE"] == "1"


def test_fit_reuses_train_py_silently(monkeypatch, tmp_path: pathlib.Path):
    called = {}

    def fake_run(command, **options):
        called.update(command=command, **options)
        return type("Done", (), {"returncode": 0})()

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    R.fit(tmp_path / "active", {"max_length": 128}, tmp_path / "data", tmp_path / "out")
    command = called["command"]
    assert pathlib.Path(command[1]).name == "train.py"
    assert command[command.index("--epochs") + 1] == "2"
    assert called["stdout"] == called["stderr"] == R.subprocess.DEVNULL


def test_api_sends_ops_headers_and_encodes_offset():
    sent = {}

    class Opener:
        def open(self, request, timeout):
            sent.update(url=request.full_url, headers=dict(request.header_items()))
            response = io.BytesIO(b'{"count": 0}')
            response.status = 200
            return response

    api = R.Api(R.Config.from_env(ENV))
    api.opener = Opener()
    api.get("http://learning", "/x", since="2026-11-15T03:00:00+09:00", until=None)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(sent["url"]).query)
    assert query == {"since": ["2026-11-15T03:00:00+09:00"]}
    headers = {key.lower(): value for key, value in sent["headers"].items()}
    assert headers["x-internal-token"] == TOKEN and headers["x-user-role"] == "SYSTEM"
