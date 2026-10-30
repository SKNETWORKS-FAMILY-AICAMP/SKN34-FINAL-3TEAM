"""#152 실제 worker/core/learning/PG/RabbitMQ/MinIO, AI 응답만 합성 대역.

#47 관리자 API는 아직 미연결이므로 검증 생산자가 core job을 seed하고 v1 명령을 발행한다.
"""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import aio_pika
import boto3
import httpx
import psycopg
from app.messaging.envelope import EventEnvelope
from botocore.config import Config
from scenario import BUCKET, DSN, NAME, seed, wait_for


def state(job):
    with psycopg.connect(DSN + "core_db") as db:
        return db.execute(
            "SELECT status,report_id FROM report_job WHERE id=%s", (job,)
        ).fetchone()


async def await_core(job, status):
    async with asyncio.timeout(30):
        while (row := state(job)) is None or row[0] != status:
            await asyncio.sleep(0.1)


def snapshot(student):
    with psycopg.connect(DSN + "report_db") as db:
        reports = db.execute(
            "SELECT id,job_id,revision,status,to_jsonb(w) FROM weekly_report w "
            "WHERE student_id=%s ORDER BY revision",
            (student,),
        ).fetchall()
        files = db.execute(
            "SELECT report_id,s3_key FROM report_file WHERE report_id IN "
            "(SELECT id FROM weekly_report WHERE student_id=%s) ORDER BY s3_key",
            (student,),
        ).fetchall()
        return reports, files


async def scenario(s3):
    student = uuid4()
    with psycopg.connect(DSN + "core_db", autocommit=True) as db:
        db.execute(
            "INSERT INTO student(id,nickname,grade,birth_year,is_demo,status,created_at,"
            "updated_at,pin_failed_count) VALUES(%s,%s,5,2015,false,'ACTIVE',now(),now(),0)",
            (student, NAME),
        )
    seed(student)
    events, requests, cases = [], [], []
    connection = await aio_pika.connect_robust(
        "amqp://verify:synthetic-only@rabbitmq:5672/"
    )
    async with connection, httpx.AsyncClient(timeout=30) as http:
        channel = await connection.channel(publisher_confirms=True)
        commands = await channel.get_exchange("cmd.direct")
        topic = await channel.get_exchange("events.topic")
        sink = await channel.declare_queue(exclusive=True, auto_delete=True)
        await sink.bind(topic, "report.*")

        async def publish(body, exchange=commands):
            await exchange.publish(
                aio_pika.Message(
                    json.dumps(body).encode(),
                    message_id=body["id"],
                    content_type="application/json",
                    delivery_mode=2,
                ),
                routing_key=body["type"],
                mandatory=True,
            )

        async def generate(
            label,
            enabled,
            mode="valid",
            failure=False,
            duplicate=False,
            trigger="ADMIN_RETRY",
        ):
            (
                await http.post(f"http://fixture:8010/test/mode/{mode}")
            ).raise_for_status()
            job = uuid4()
            # core #47의 향후 접수/감사/원작업 연결 기능을 대역 결과로 완료 처리하지 않는다.
            with psycopg.connect(DSN + "core_db", autocommit=True) as db:
                db.execute(
                    "INSERT INTO report_job(id,student_id,period_from,period_to,trigger,status,"
                    "retry_count,created_at) VALUES(%s,%s,'2026-10-19','2026-10-25',%s,'QUEUED',0,now())",
                    (job, student, trigger),
                )
            body = EventEnvelope(
                type="report.generate",
                source="core-service",
                subject=str(student),
                dataschema="report.generate.v1",
                data={
                    "jobId": str(job),
                    "studentId": str(student),
                    "periodFrom": "2026-10-19",
                    "periodTo": "2026-10-25",
                    "trigger": trigger,
                    "narrativeEnabled": enabled,
                },
            ).model_dump(mode="json")
            requests.append(body)
            await publish(body)
            if duplicate:
                await publish(body)
                another = deepcopy(body)
                another["id"] = str(uuid4())
                await publish(another)
            received = []
            async with asyncio.timeout(120):
                while not any(
                    x["type"] in {"report.completed", "report.failed"} for x in received
                ):
                    message = await sink.get(fail=False)
                    if message is None:
                        await asyncio.sleep(0.1)
                        continue
                    event = json.loads(message.body)
                    await message.ack()
                    assert event["data"]["jobId"] == str(job), event
                    received.append(event)
            terminal = "FAILED" if failure else "COMPLETED"
            assert {x["type"] for x in received} == {
                "report.started",
                "report.failed" if failure else "report.completed",
            }
            events.extend(received)
            await await_core(job, terminal)
            reports, files = snapshot(student)
            current = [x for x in reports if x[1] == job]
            assert len(current) == 1 and current[0][3] == terminal
            report_id = current[0][0]
            assert all(x["data"]["reportId"] == str(report_id) for x in received)
            assert state(job)[1] == report_id
            assert len([x for x in files if x[0] == report_id]) == (0 if failure else 3)
            calls = (await http.get("http://fixture:8010/test/calls")).json()
            assert len(calls) == (1 if enabled else 0)
            with psycopg.connect(DSN + "core_db") as db:
                execution = db.execute(
                    "SELECT status FROM job_execution WHERE job_type='REPORT' AND job_id=%s",
                    (job,),
                ).fetchall()
                assert execution == [(terminal,)]
            cases.append(
                {
                    "case": label,
                    "jobId": str(job),
                    "reportId": str(report_id),
                    "status": terminal,
                    "revision": current[0][2],
                    "aiCalls": len(calls),
                }
            )
            print("PASS " + label, flush=True)
            return body, received

        baseline, _ = await generate(
            "existing completed revision and real files", False, trigger="SCHEDULE"
        )
        baseline_rows, baseline_files = snapshot(student)
        file_bytes = {
            key: s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            for _, key in baseline_files
        }
        original, original_events = await generate(
            "original AI failure", True, mode="unavailable", failure=True
        )
        old_rows, _ = snapshot(student)
        retry, retry_events = await generate(
            "new job retries failed job successfully; duplicate delivery",
            True,
            duplicate=True,
        )
        await generate(
            "another new job can fail again", True, mode="unavailable", failure=True
        )
        await generate(
            "new free retry uses current false entitlement and skips AI", False
        )

        before = snapshot(student)
        # 원래 실패 작업과 완료 작업의 지연된 명령은 새 이벤트 ID여도 재실행하지 않는다.
        for old in (original, baseline, retry):
            redelivery = deepcopy(old)
            redelivery["id"] = str(uuid4())
            requests.append(redelivery)
            await publish(redelivery)

        # 원작업의 중복/지연 결과 및 완료된 새 작업의 늦은 started를 실제 core에 전달한다.
        injected = [
            deepcopy(original_events[-1]),
            deepcopy(original_events[0]),
            deepcopy(retry_events[0]),
        ]
        for event in injected:
            event["id"] = str(uuid4())
            await publish(event, topic)
        async with asyncio.timeout(30):
            while True:
                with psycopg.connect(DSN + "core_db") as db:
                    seen = db.execute(
                        "SELECT count(*) FROM processed_event WHERE event_id = ANY(%s::uuid[])",
                        ([x["id"] for x in injected],),
                    ).fetchone()[0]
                if seen == len(injected):
                    break
                await asyncio.sleep(0.2)
        assert state(original["data"]["jobId"])[0] == "FAILED"
        assert state(retry["data"]["jobId"])[0] == "COMPLETED"
        cases.append(
            {
                "case": "real core ignores late original results and late started after completion"
            }
        )

        # 두 worker 경합으로 생길 수 있는 기존 retry.1 메시지까지 소진한 뒤 중복 여부 검사.
        queue_samples = []
        async with asyncio.timeout(85):
            while True:
                queues = [
                    await channel.declare_queue(
                        "report.report.generate" + suffix, passive=True
                    )
                    for suffix in ("", ".retry.1")
                ]
                # RobustChannel은 같은 passive queue 객체를 캐시한다.
                # declaration_result 재사용 대신 실제 브로커에 다시 조회한다.
                counts = [(await q.declare()).message_count for q in queues]
                if not queue_samples or queue_samples[-1] != counts:
                    queue_samples.append(counts)
                    print("QUEUE_COUNTS=" + json.dumps(counts), flush=True)
                if all(count == 0 for count in counts):
                    break
                await asyncio.sleep(0.5)
        await asyncio.sleep(1)
        after = snapshot(student)
        assert after == before
        assert [r[2] for r in after[0]] == [1, 2, 3, 4, 5]
        assert after[0][0] == baseline_rows[0] and after[0][1] == old_rows[1]
        for key, expected in file_bytes.items():
            assert s3.get_object(Bucket=BUCKET, Key=key)["Body"].read() == expected
        with psycopg.connect(DSN + "report_db") as db:
            outbox = db.execute(
                "SELECT event_type,payload,published_at FROM outbox_event WHERE subject=%s",
                (str(student),),
            ).fetchall()
            assert len(outbox) == 10 and all(x[2] is not None for x in outbox)
        cases.append(
            {
                "case": "terminal redelivery creates no report/event; prior rows and S3 bytes preserved"
            }
        )
        cases.append(
            {
                "case": "exactly one started and terminal Outbox per job after two-worker duplicate delivery"
            }
        )
        print(
            "RESULT_JSON="
            + json.dumps(
                {
                    "verifiedAt": datetime.now(UTC).isoformat(),
                    "cases": cases,
                    "requests": requests,
                    "events": events,
                    "injectedLateEvents": injected,
                    "scope": "real core/learning/report/PG/Rabbit/MinIO; synthetic AI; admin producer seeded",
                    "duplicateQueueSamples": queue_samples,
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
