"""Disposable Compose exercise: real core/learning/report/PG/RabbitMQ/MinIO, synthetic AI."""

import asyncio
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

import aio_pika
import boto3
import httpx
import psycopg
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.messaging.envelope import EventEnvelope
from app.query.schemas import ReportDetail

TOKEN = "report56-test-only"
NAME = "합성학생비밀별명"
BUCKET = "report56-synthetic"
DSN = "postgresql://verify:synthetic-only@postgres:5432/"


def wait_for(check, label, timeout=240):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (httpx.HTTPError, BotoCoreError, ClientError) as exc:
            last_error = type(exc).__name__
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {label}; last error type={last_error}")


def headers(student):
    return {
        "X-Internal-Token": TOKEN,
        "X-User-Role": "SYSTEM",
        "X-Student-Scope": str(student),
        "X-Report-Narrative-Enabled": "true",
    }


def seed(student):
    mission, version, rubric, actor = [uuid4() for _ in range(4)]
    with psycopg.connect(DSN + "learning_db", autocommit=True) as db:
        db.execute(
            "INSERT INTO mission(id,code,status,demo_only,sort_order,"
            "created_by,created_at,updated_at) "
            "VALUES(%s,%s,'PUBLISHED',false,1,%s,now(),now())",
            (mission, str(mission), actor),
        )
        db.execute(
            "INSERT INTO mission_version(id,mission_id,version,title,subject,grade_min,grade_max,"
            "thinking_type,input_type,question,created_by,created_at) "
            "VALUES(%s,%s,1,'합성 미션','language',3,6,'ANALYZE','NARRATIVE','합성 질문',%s,now())",
            (version, mission, actor),
        )
        db.execute(
            "INSERT INTO rubric_version(id,mission_id,version,created_by,created_at) "
            "VALUES(%s,%s,1,%s,now())",
            (rubric, mission, actor),
        )
        db.execute(
            "UPDATE mission SET current_version_id=%s,current_rubric_version_id=%s WHERE id=%s",
            (version, rubric, mission),
        )
        with httpx.Client(base_url="http://learning:8081", headers=headers(student)) as client:
            response = client.post(
                f"/internal/missions/{mission}/attempts?grade=5",
                headers={"X-User-Role": "STUDENT"},
            )
            response.raise_for_status()
            attempt = response.json()["attemptId"]
            response = client.post(
                f"/internal/attempts/{attempt}/answers",
                headers={"X-User-Role": "STUDENT", "Idempotency-Key": str(uuid4())},
                json={"inputType": "NARRATIVE", "text": NAME + "은 왜냐하면 좋아요."},
            )
            response.raise_for_status()
            answer = response.json()["answerId"]
            db.execute(
                "UPDATE answer SET submitted_at='2026-10-20T10:00:00+09:00' WHERE id=%s",
                (answer,),
            )
            db.execute(
                "UPDATE judgment SET process_status='DONE',result='PARTIAL',"
                "method='LLM',trial=true "
                "WHERE answer_id=%s",
                (answer,),
            )


async def scenario(s3):
    student, empty = uuid4(), uuid4()
    deleted, missing = uuid4(), uuid4()
    with psycopg.connect(DSN + "core_db", autocommit=True) as db:
        for target, status in ((student, "ACTIVE"), (empty, "ACTIVE"), (deleted, "DELETED")):
            db.execute(
                "INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,"
                "created_at,updated_at,pin_failed_count) "
                "VALUES(%s,%s,5,2015,false,%s,now(),now(),0)",
                (target, NAME, status),
            )
    seed(student)
    events, results, requests = [], [], []
    connection = await aio_pika.connect_robust("amqp://verify:synthetic-only@rabbitmq:5672/")
    async with connection, httpx.AsyncClient(timeout=30) as http:
        channel = await connection.channel(publisher_confirms=True)
        commands = await channel.get_exchange("cmd.direct")
        topic = await channel.get_exchange("events.topic")
        sink = await channel.declare_queue(durable=True, auto_delete=True, exclusive=True)
        await sink.bind(topic, "report.*")

        profile_url = f"http://core:8080/internal/students/{student}/profile"
        response = await http.get(profile_url, headers=headers(student))
        assert response.status_code == 200 and response.json() == {
            "studentId": str(student),
            "nickname": NAME,
        }
        assert "no-store" in response.headers["cache-control"]
        for auth, expected in (
            ({}, 401),
            ({**headers(student), "X-User-Role": "PARENT"}, 403),
            (headers(uuid4()), 403),
        ):
            assert (await http.get(profile_url, headers=auth)).status_code == expected

        async def case(label, target, enabled, mode="valid", failure=False, duplicate=False):
            response = await http.post(f"http://fixture:8010/test/mode/{mode}")
            response.raise_for_status()
            job = uuid4()
            body = EventEnvelope(
                type="report.generate",
                source="core-service",
                subject=str(target),
                dataschema="report.generate.v1",
                data={
                    "jobId": str(job),
                    "studentId": str(target),
                    "periodFrom": "2026-10-19",
                    "periodTo": "2026-10-25",
                    "trigger": "SCHEDULE",
                    "narrativeEnabled": enabled,
                },
            ).model_dump(mode="json")
            requests.append(body)
            for _ in range(2 if duplicate else 1):
                await commands.publish(
                    aio_pika.Message(
                        json.dumps(body).encode(),
                        content_type="application/json",
                        message_id=body["id"],
                        delivery_mode=2,
                    ),
                    routing_key="report.generate",
                    mandatory=True,
                )
            received = []
            async with asyncio.timeout(120):
                while not any(e["type"] in {"report.completed", "report.failed"} for e in received):
                    message = await sink.get(fail=False)
                    if message is None:
                        await asyncio.sleep(0.1)
                        continue
                    event = json.loads(message.body)
                    await message.ack()
                    assert event["data"]["jobId"] == str(job), event
                    received.append(event)
            assert {e["type"] for e in received} == {
                "report.started",
                "report.failed" if failure else "report.completed",
            }
            events.extend(received)
            with psycopg.connect(DSN + "report_db") as db:
                row = db.execute(
                    "SELECT id,status,state FROM weekly_report WHERE job_id=%s", (job,)
                ).fetchone()
                assert row and row[1] == ("FAILED" if failure else "COMPLETED")
                assert (
                    db.execute(
                        "SELECT count(*) FROM weekly_report WHERE job_id=%s", (job,)
                    ).fetchone()[0]
                    == 1
                )
                report_id = str(row[0])
                files = db.execute(
                    "SELECT count(*) FROM report_file WHERE report_id=%s", (row[0],)
                ).fetchone()[0]
                assert files == (0 if failure else 3)
            captured = (await http.get("http://fixture:8010/test/calls")).json()
            assert len(captured) == (1 if enabled and target == student else 0)
            for call in captured:
                assert call["scope"] == str(target)
                serialized = json.dumps(call["body"], ensure_ascii=False)
                assert NAME not in serialized and str(target) not in serialized
                assert "[학생]" in serialized
            detail = None
            if not failure:
                response = await http.get(
                    f"http://report-api:8002/internal/reports/{report_id}",
                    headers=headers(target),
                )
                response.raise_for_status()
                detail = response.json()
                ReportDetail.model_validate(detail)
                assert detail["status"] == "COMPLETED"
                if target == empty:
                    assert detail["state"] == "NO_RECORD" and row[2] == "NO_RECORD"
                if not enabled or target == empty:
                    assert detail["narrative"] is None
                else:
                    assert detail["narrative"]["source"] == (
                        "TEMPLATE" if mode == "mismatch" else "LLM"
                    )
                listing = await http.get(
                    "http://report-api:8002/internal/reports",
                    params={"studentId": str(target)},
                    headers=headers(target),
                )
                listing.raise_for_status()
                assert any(item["reportId"] == report_id for item in listing.json()["items"])
                for format in ("pdf", "md", "html"):
                    response = await http.get(
                        f"http://report-api:8002/internal/reports/{report_id}/files/{format}",
                        headers=headers(target),
                    )
                    response.raise_for_status()
                    download = await http.get(response.json()["url"])
                    download.raise_for_status()
                    assert (
                        download.content.startswith(b"%PDF")
                        if format == "pdf"
                        else NAME in download.text
                    )
                forbidden = await http.get(
                    f"http://report-api:8002/internal/reports/{report_id}",
                    headers=headers(uuid4()),
                )
                assert forbidden.status_code == 403
            results.append(
                {
                    "case": label,
                    "status": row[1],
                    "state": row[2],
                    "fileRows": files,
                    "aiCalls": len(captured),
                    "detail": detail,
                }
            )
            print("PASS " + label, flush=True)

        await case(
            "paid + duplicate + privacy + files + scoped query",
            student,
            True,
            duplicate=True,
        )
        await case("free skips AI", student, False)
        await case("NO_RECORD completes without AI", empty, True)
        await case("deleted core student fails before AI", deleted, True, failure=True)
        await case("missing core student fails before AI", missing, True, failure=True)
        await case("numeric mismatch uses TEMPLATE", student, True, mode="mismatch")
        await case(
            "AI 503 fails without TEMPLATE",
            student,
            True,
            mode="unavailable",
            failure=True,
        )
        # Only this isolated, explicitly named synthetic bucket is removed for fault injection.
        assert BUCKET == "report56-synthetic"
        objects = s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])
        assert all(obj["Key"].startswith("reports/") for obj in objects)
        if objects:
            s3.delete_objects(
                Bucket=BUCKET,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
            )
        s3.delete_bucket(Bucket=BUCKET)
        await case("MinIO missing bucket fails without file rows", student, False, failure=True)
        print(
            "RESULT_JSON="
            + json.dumps(
                {
                    "verifiedAt": datetime.now(UTC).isoformat(),
                    "cases": results,
                    "requests": requests,
                    "events": events,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    for url in (
        "http://core:8080/actuator/health/readiness",
        "http://learning:8081/actuator/health/readiness",
        "http://report-api:8002/health/ready",
        "http://fixture:8010/test/calls",
    ):
        wait_for(lambda url=url: httpx.get(url).status_code == 200, url)
    s3 = boto3.client(
        "s3", endpoint_url="http://minio:9000", config=Config(signature_version="s3v4")
    )
    wait_for(lambda: s3.list_buckets(), "MinIO")
    s3.create_bucket(Bucket=BUCKET)
    asyncio.run(scenario(s3))
