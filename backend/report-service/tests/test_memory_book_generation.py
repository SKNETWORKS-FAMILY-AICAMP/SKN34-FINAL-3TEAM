"""추억 그림책 생성·파일 주소 (docs/proposals/memory-book.md, 미도입 시험 구현).

데이터는 모두 지어낸 값.
"""

import asyncio
import base64
import io
import re
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader

from app.bootstrap import create_app
from app.clients.asset_fetcher import AssetFetcher, parse_internal_origins, parse_origins
from app.clients.memory_book_client import (
    MemoryBookLearningClient,
    MemoryBookRound,
    MemoryBookRoundNotFound,
)
from app.clients.storage import ObjectStorage, memory_book_key, memory_book_prefix
from app.deletion.state import deletion_guard
from app.generation.records import RecordContractError
from app.memory_book.consumer import MemoryBookConsumer
from app.memory_book.models import GenerateMemoryBook
from app.memory_book.router import MemoryBookFiles, memory_book_files
from app.memory_book.service import MemoryBookService
from app.messaging.contracts import InvalidEvent
from app.messaging.envelope import EventEnvelope
from app.security import UserContext, bind_user_context, current_user_context, reset_user_context
from scripts.memory_book_sample import placeholder_png

PNG = placeholder_png(8, 8, (200, 100, 50), (50, 100, 200))
WEEK = date(2026, 11, 2)
ORIGIN = "https://assets.test"


def round_json(student_id=None, *, seen=True, theme_id=None, image=f"{ORIGIN}/theme-drafts/r/X"):
    days = []
    for index, day in enumerate(("MON", "TUE", "WED", "THU", "FRI")):
        days.append(
            {
                "day": day,
                "missionId": str(uuid4()),
                "title": f"문제 {index + 1}",
                "thinkingType": ("ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT")[index],
                "question": f"질문 {index + 1}",
                "sceneImage": image,
                "dialogue": [{"speaker": "등대지기", "text": "바람이 셌단다"}],
                "attempt": {
                    "attemptId": str(uuid4()),
                    "completedAt": "2026-11-03T01:00:00Z",
                    "answers": [
                        {"version": 1, "text": f"답 {index + 1}", "followup": None},
                        {
                            "version": 2,
                            "text": f"보완 답 {index + 1}",
                            "followup": {"type": "TELL_MORE", "question": "왜 그럴까?"},
                        },
                    ],
                    "reflection": {"difficulty": "NORMAL", "text": "다시 봤어요"},
                },
            }
        )
    return {
        "themeId": str(theme_id or THEME),
        "weekStart": WEEK.isoformat(),
        "themeVersionId": str(uuid4()),
        "title": "등대 불빛",
        "intro": "불빛이 꺼졌어요",
        "introImage": image,
        "bigQuestion": "왜 꺼졌을까?",
        "days": days,
        "ending": {
            "seen": seen,
            "outro": "빗장을 달았어요" if seen else None,
            "answer": "바람" if seen else None,
            "outroImage": image if seen else None,
        },
    }


THEME = uuid4()


# ---------------------------------------------------------------- 명령 소비


def envelope(student, data=None, **overrides):
    values = {
        "id": str(uuid4()),
        "type": "memorybook.generate",
        "source": "core-service",
        "subject": str(student),
        "dataschema": "memorybook.generate.v1",
        "time": datetime(2026, 11, 23, tzinfo=UTC),
        "data": data
        if data is not None
        else {
            "bookId": str(uuid4()),
            "studentId": str(student),
            "rounds": [{"themeId": str(THEME), "weekStart": WEEK.isoformat()}],
        },
    }
    values.update(overrides)
    return EventEnvelope[dict](**values)


def test_consumer_binds_system_scope_and_decodes_one_round():
    student, seen = uuid4(), []

    class Service:
        async def generate(self, command):
            context = current_user_context()
            seen.append((command, context.role, context.student_scope))

    asyncio.run(MemoryBookConsumer(Service())(envelope(student)))
    command, role, scope = seen[0]
    assert (command.student_id, command.theme_id, command.week_start) == (student, THEME, WEEK)
    assert role == "SYSTEM" and scope == frozenset({str(student)})
    assert current_user_context() is None


@pytest.mark.parametrize(
    "change",
    [
        {"type": "report.generate"},
        {"source": "learning-service"},
        {"dataschema": "memorybook.generate.v2"},
        {"subject": str(uuid4())},
    ],
)
def test_consumer_rejects_wrong_identity(change):
    student = uuid4()
    with pytest.raises(InvalidEvent):
        asyncio.run(MemoryBookConsumer(None)(envelope(student, **change)))


@pytest.mark.parametrize(
    "rounds",
    [
        [],
        [{"themeId": str(THEME), "weekStart": "2026-11-03"}],
        [{"themeId": str(THEME), "weekStart": WEEK.isoformat()}] * 2,
        [{"themeId": "not-a-uuid", "weekStart": WEEK.isoformat()}],
    ],
)
def test_consumer_rejects_invalid_rounds(rounds):
    student = uuid4()
    data = {"bookId": str(uuid4()), "studentId": str(student), "rounds": rounds}
    with pytest.raises(InvalidEvent):
        asyncio.run(MemoryBookConsumer(None)(envelope(student, data)))


# ---------------------------------------------------------------- 그림 받기


def fetch(handler, url, **options):
    async def scenario():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            fetcher = AssetFetcher(
                client, parse_origins(f"{ORIGIN}, http://127.0.0.1:19000"), **options
            )
            session = fetcher.session()
            if isinstance(url, list):
                return [await session.data_uri(u) for u in url]
            return await session.data_uri(url)

    return asyncio.run(scenario())


def test_allowed_png_becomes_data_uri_without_internal_headers():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=PNG, headers={"content-type": "text/plain"})

    value = fetch(handler, f"{ORIGIN}/theme-drafts/r/INTRO?X-Amz-Signature=abc")
    assert value == "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert "x-internal-token" not in requests[0].headers
    assert "x-student-scope" not in requests[0].headers


@pytest.mark.parametrize(
    "url,response",
    [
        ("https://evil.test/x.png", httpx.Response(200, content=PNG)),
        ("http://assets.test/x.png", httpx.Response(200, content=PNG)),  # 다른 scheme
        (f"{ORIGIN}/x.png", httpx.Response(302, headers={"location": f"{ORIGIN}/y.png"})),
        (f"{ORIGIN}/x.png", httpx.Response(403)),
        (f"{ORIGIN}/x.svg", httpx.Response(200, content=b"<svg></svg>")),
        (f"{ORIGIN}/x.png", httpx.Response(200, content=b"\x89PNG" + b"0" * 2000)),
        ("/relative/path.png", httpx.Response(200, content=PNG)),
        ("theme-drafts/r/INTRO", httpx.Response(200, content=PNG)),
    ],
)
def test_rejected_images_become_none(url, response):
    assert fetch(lambda request: response, url, max_bytes=1000) is None


def test_size_limits_per_image_and_per_book():
    big = PNG + b"0" * 600
    assert fetch(lambda r: httpx.Response(200, content=big), f"{ORIGIN}/a", max_bytes=500) is None
    values = fetch(
        lambda r: httpx.Response(200, content=PNG),
        [f"{ORIGIN}/a", f"{ORIGIN}/b", f"{ORIGIN}/c"],
        total_bytes=len(PNG) * 2,
    )
    assert values[0] and values[1] and values[2] is None


def test_internal_origin_keeps_signed_host_header():
    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers["host"]))
        return httpx.Response(200, content=PNG)

    value = fetch(
        handler,
        "http://127.0.0.1:19000/bucket/theme-drafts/r/INTRO?X-Amz-Signature=abc",
        internal_origins=parse_internal_origins(
            "http://127.0.0.1:19000=http://minio.platform.svc.cluster.local:9000"
        ),
    )
    assert value is not None
    assert seen == [
        (
            "http://minio.platform.svc.cluster.local:9000/bucket/theme-drafts/r/INTRO?X-Amz-Signature=abc",
            "127.0.0.1:19000",
        )
    ]


# ---------------------------------------------------------------- learning 조립 응답


def learning(handler, student, role="SYSTEM"):
    async def scenario():
        reset = bind_user_context(UserContext(None, role, frozenset({str(student)})))
        try:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(base_url="http://learning.test", transport=transport) as c:
                return await MemoryBookLearningClient(c).round(student, THEME, WEEK)
        finally:
            reset_user_context(reset)

    return asyncio.run(scenario())


def test_learning_round_path_and_shape():
    student, paths = uuid4(), []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json=round_json())

    result = learning(handler, student)
    assert paths == [f"/internal/students/{student}/memory-book/{THEME}/{WEEK}"]
    assert isinstance(result, MemoryBookRound) and len(result.days) == 5


def test_learning_round_errors():
    student = uuid4()
    with pytest.raises(MemoryBookRoundNotFound):
        learning(lambda r: httpx.Response(404, json={"code": "THEME_FRAME_NOT_FOUND"}), student)
    with pytest.raises(RecordContractError):
        learning(lambda r: httpx.Response(200, json={"title": "모양이 다름"}), student)
    leaked = round_json(seen=False)
    leaked["ending"]["answer"] = "바람"
    with pytest.raises(RecordContractError):
        learning(lambda r: httpx.Response(200, json=leaked), student)
    with pytest.raises(RecordContractError):
        learning(lambda r: httpx.Response(200, json=round_json(theme_id=uuid4())), student)
    with pytest.raises(RecordContractError):
        learning(lambda r: httpx.Response(200, json=round_json()), student, role="PARENT")
    with pytest.raises(httpx.HTTPStatusError):
        learning(lambda r: httpx.Response(503), student)


# ---------------------------------------------------------------- 생성 서비스


class Locks:
    def __init__(self):
        self.acquired = []

    def acquire(self, job_id, student_id=None):
        self.acquired.append((job_id, student_id))
        return SimpleNamespace(close=lambda: None)


class Profiles:
    def __init__(self, shared=True):
        self.shared = shared

    async def lookup(self, student_id):
        return SimpleNamespace(nickname="합성학생", parent_sharing_enabled=self.shared)


class Learning:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    async def round(self, student_id, theme_id, week_start):
        self.calls += 1
        if self.error:
            raise self.error
        return MemoryBookRound.model_validate(self.result)


class Assets:
    def __init__(self):
        self.urls = []

    def session(self):
        outer = self

        class Session:
            async def data_uri(self, url):
                outer.urls.append(url)
                return "data:image/png;base64," + base64.b64encode(PNG).decode() if url else None

        return Session()


class Outbox:
    def __init__(self):
        self.events = []

    def add(self, session, envelope):
        self.events.append(envelope)


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="synthetic",
            aws_secret_access_key="synthetic",
        )
        client.create_bucket(Bucket="synthetic-reports")
        yield ObjectStorage(client, "synthetic-reports")


def run_service(factory, storage, student, *, profiles=None, learning_=None, assets=None):
    outbox, locks = Outbox(), Locks()
    service = MemoryBookService(
        factory,
        locks,
        profiles or Profiles(),
        learning_ or Learning(round_json()),
        assets or Assets(),
        lambda: storage,
        outbox=outbox,
    )
    command = GenerateMemoryBook(uuid4(), student, THEME, WEEK, datetime.now(UTC))

    async def scenario():
        reset = bind_user_context(UserContext(None, "SYSTEM", frozenset({str(student)})))
        try:
            await service.generate(command)
        finally:
            reset_user_context(reset)

    asyncio.run(scenario())
    return command, outbox.events, locks


def pdf_text(body):
    return re.sub(r"\s+", "", "".join(p.extract_text() for p in PdfReader(io.BytesIO(body)).pages))


def test_generate_stores_pdf_and_announces_ready(db_session_factory, s3):
    student, assets, learning_ = uuid4(), Assets(), Learning(round_json())
    command, events, locks = run_service(
        db_session_factory, s3, student, assets=assets, learning_=learning_
    )

    key = memory_book_key(student, command.book_id)
    assert key == f"reports/{student}/memory-books/{command.book_id}/pdf"
    body = s3._client.get_object(Bucket="synthetic-reports", Key=key)["Body"].read()
    text = pdf_text(body)
    assert "합성학생의추억그림책" in text and "보완답1" in text and "큰질문의답:바람" in text
    assert len(assets.urls) == 7  # 시작 + 요일 5 + 종료
    assert locks.acquired == [(command.book_id, student)]
    [event] = events
    assert (event.type, event.source, event.subject) == (
        "memorybook.completed",
        "report-service",
        str(student),
    )
    assert event.data["status"] == "READY" and event.data["sizeBytes"] == len(body)
    assert UUID(event.data["themeVersionId"])


def test_before_ending_does_not_fetch_outro_image(db_session_factory, s3):
    assets = Assets()
    run_service(
        db_session_factory, s3, uuid4(), assets=assets, learning_=Learning(round_json(seen=False))
    )
    assert len(assets.urls) == 6


def test_private_student_fails_without_calling_learning(db_session_factory, s3):
    student, learning_ = uuid4(), Learning(round_json())
    command, events, _ = run_service(
        db_session_factory, s3, student, profiles=Profiles(shared=False), learning_=learning_
    )
    assert learning_.calls == 0
    assert not s3.exists(memory_book_key(student, command.book_id))
    assert events[0].data == {
        "bookId": str(command.book_id),
        "studentId": str(student),
        "status": "FAILED",
        "failureCode": "STUDENT_RECORDS_PRIVATE",
    }


@pytest.mark.parametrize(
    "error,code",
    [
        (MemoryBookRoundNotFound(), "THEME_FRAME_NOT_FOUND"),
        (RecordContractError("x"), "INVALID_ROUND"),
    ],
)
def test_permanent_learning_failures_are_announced(db_session_factory, s3, error, code):
    _, events, _ = run_service(db_session_factory, s3, uuid4(), learning_=Learning(error=error))
    assert (events[0].data["status"], events[0].data["failureCode"]) == ("FAILED", code)


def test_transient_learning_failure_raises_for_queue_retry(db_session_factory, s3):
    request = httpx.Request("GET", "http://learning.test")
    error = httpx.HTTPStatusError("503", request=request, response=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        run_service(db_session_factory, s3, uuid4(), learning_=Learning(error=error))


def test_redelivery_reuses_existing_file(db_session_factory, s3):
    student = uuid4()
    book = uuid4()
    s3.put(memory_book_key(student, book), b"%PDF-existing", "application/pdf")
    learning_, outbox = Learning(round_json()), Outbox()
    service = MemoryBookService(
        db_session_factory, Locks(), Profiles(), learning_, Assets(), lambda: s3, outbox=outbox
    )

    async def scenario():
        reset = bind_user_context(UserContext(None, "SYSTEM", frozenset({str(student)})))
        try:
            await service.generate(
                GenerateMemoryBook(book, student, THEME, WEEK, datetime.now(UTC))
            )
        finally:
            reset_user_context(reset)

    asyncio.run(scenario())
    assert learning_.calls == 0
    assert outbox.events[0].data["status"] == "READY"


def test_deleted_student_is_announced_and_nothing_is_rendered(db_session_factory, s3):
    student, learning_ = uuid4(), Learning(round_json())
    with db_session_factory.begin() as session:
        session.execute(
            deletion_guard.insert().values(
                student_id=student,
                scope="RECORDS",
                cutoff_at=datetime(2099, 1, 1, tzinfo=UTC),
                deletion_request_id=uuid4(),
                status="COMPLETED",
                updated_at=datetime.now(UTC),
            )
        )
    _, events, _ = run_service(db_session_factory, s3, student, learning_=learning_)
    assert learning_.calls == 0
    assert events[0].data["failureCode"] == "STUDENT_DELETED"


# ---------------------------------------------------------------- 저장 키·삭제·파일 주소


def test_memory_book_prefix_can_be_deleted_alone_and_with_student(s3):
    student, book, other = uuid4(), uuid4(), uuid4()
    s3.put(memory_book_key(student, book), b"a", "application/pdf")
    s3.put(memory_book_key(student, other), b"b", "application/pdf")
    s3.delete_prefix(memory_book_prefix(student, book))
    assert not s3.exists(memory_book_key(student, book))
    assert s3.exists(memory_book_key(student, other))
    s3.delete_prefix(f"reports/{student}/")
    assert not s3.exists(memory_book_key(student, other))
    for unsafe in (f"reports/{student}/memory-books/", f"reports/{student}/memory-books/x/"):
        with pytest.raises(ValueError):
            s3.delete_prefix(unsafe)


@pytest.fixture
def files_api(report_factory):
    app = create_app()
    storage = SimpleNamespace(
        existing=set(),
        signed=[],
        exists=lambda key: key in storage.existing,
        presigned_url=lambda key, ttl, filename: (
            storage.signed.append((key, ttl, filename))
            or {"url": "https://synthetic.invalid/book", "expiresAt": "2026-11-23T00:05:00+00:00"}
        ),
    )
    app.dependency_overrides[memory_book_files] = lambda: MemoryBookFiles(
        report_factory, lambda: storage, 300
    )
    with TestClient(app) as client:
        yield client, storage


def test_file_url_requires_student_scope_and_existing_file(files_api, report_student_id):
    client, storage = files_api
    book = uuid4()
    path = f"/internal/students/{report_student_id}/memory-books/{book}/files/pdf"
    headers = {"X-Internal-Token": "test-token", "X-User-Role": "STUDENT"}

    assert client.get(path, headers={**headers, "X-Student-Scope": str(uuid4())}).status_code == 403
    missing = client.get(path, headers={**headers, "X-Student-Scope": str(report_student_id)})
    assert missing.status_code == 404

    storage.existing.add(memory_book_key(report_student_id, book))
    ok = client.get(path, headers={**headers, "X-Student-Scope": str(report_student_id)})
    assert ok.status_code == 200 and ok.json()["url"] == "https://synthetic.invalid/book"
    assert storage.signed == [
        (memory_book_key(report_student_id, book), 300, f"memory-book-{book}.pdf")
    ]


def test_file_path_is_core_only():
    from app.security import caller_permits

    student, book = uuid4(), uuid4()
    path = f"/internal/students/{student}/memory-books/{book}/files/pdf"
    assert caller_permits("core", path)
    assert not caller_permits("core", f"/internal/students/{student}/memory-books/{book}/files/md")
    assert not caller_permits("core", f"/internal/students/{student}/memory-books/../x/files/pdf")
