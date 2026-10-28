"""Real #27 -> report verification, using disposable Docker services and synthetic data.

Run with report-service/.venv Python after rebuilding learning's bootJar.
No shared DB, credentials, AI service, production data, or external writes are used.
"""

import argparse
import asyncio
import io
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import docker
import httpx
import psycopg
import yaml
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "backend/report-service"
sys.path.insert(0, str(REPORT))


def wait_for(check, label, timeout=120):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (httpx.HTTPError, psycopg.Error, OSError) as exc:
            last = type(exc).__name__
        time.sleep(0.5)
    raise RuntimeError(f"{label} not ready; last error type={last}")


def verify(output):
    jar = (
        ROOT / "backend/learning-service/build/libs/learning-service-0.0.1-SNAPSHOT.jar"
    )
    sources = list((ROOT / "backend/learning-service/src/main").rglob("*"))
    if not jar.exists() or any(
        p.is_file() and p.stat().st_mtime > jar.stat().st_mtime for p in sources
    ):
        raise RuntimeError("Build learning bootJar from current sources first")
    output.mkdir(parents=True, exist_ok=True)
    results = []

    def passed(name):
        results.append(name)
        print(f"PASS {name}", flush=True)

    def save(name, body):
        (output / name).write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    client = docker.from_env()
    with ExitStack() as cleanup:
        network = client.networks.create(f"report27-{uuid4().hex[:10]}")
        cleanup.callback(network.remove)

        def run(image, name, **kwargs):
            container = client.containers.run(
                image,
                name=f"{network.name}-{name}",
                network=network.name,
                detach=True,
                **kwargs,
            )
            cleanup.callback(container.remove, force=True, v=True)

            def logs():
                (output / f"{name}.log").write_bytes(container.logs())

            cleanup.callback(logs)
            return container

        def port(container, number):
            container.reload()
            return container.attrs["NetworkSettings"]["Ports"][f"{number}/tcp"][0][
                "HostPort"
            ]

        password, token = "synthetic-local-only", "report27-local-verification"
        pg = run(
            "postgres:17.11-alpine",
            "db",
            environment={
                "POSTGRES_USER": "verify",
                "POSTGRES_PASSWORD": password,
                "POSTGRES_DB": "report27_learning",
            },
            ports={"5432/tcp": ("127.0.0.1", None)},
        )
        rabbit = run(
            "rabbitmq:4.3.7-management-alpine",
            "rabbit",
            environment={
                "RABBITMQ_DEFAULT_USER": "verify",
                "RABBITMQ_DEFAULT_PASS": password,
            },
            ports={"5672/tcp": ("127.0.0.1", None)},
        )
        dsn = f"postgresql://verify:{password}@127.0.0.1:{port(pg, 5432)}/report27_learning"

        def db_ready():
            with psycopg.connect(dsn) as connection:
                return connection.execute("SELECT 1").fetchone() == (1,)

        wait_for(db_ready, "PostgreSQL")
        db = cleanup.enter_context(psycopg.connect(dsn, autocommit=True))
        assert (
            db.execute("SELECT current_database()").fetchone()[0] == "report27_learning"
        )
        db.execute("CREATE DATABASE report27_report")
        migration = run(
            "flyway/flyway:13.11.1-alpine",
            "migrate",
            command=[
                f"-url=jdbc:postgresql://{pg.name}:5432/report27_learning",
                "-user=verify",
                f"-password={password}",
                "migrate",
            ],
            volumes={
                str(
                    ROOT / "backend/learning-service/src/main/resources/db/migration"
                ): {"bind": "/flyway/sql", "mode": "ro"}
            },
        )
        assert migration.wait(timeout=120)["StatusCode"] == 0, (
            "Learning migration failed"
        )
        learning = run(
            "eclipse-temurin:21-jdk",
            "learning",
            command=[
                "java",
                "-Xmx512m",
                "-jar",
                "/app/learning.jar",
            ],
            user="10001",
            environment={
                "DB_URL": f"jdbc:postgresql://{pg.name}:5432/report27_learning",
                "DB_USERNAME": "verify",
                "DB_PASSWORD": password,
                "INTERNAL_TOKEN": token,
                "RABBITMQ_HOST": rabbit.name,
                "RABBITMQ_USERNAME": "verify",
                "RABBITMQ_PASSWORD": password,
            },
            volumes={str(jar): {"bind": "/app/learning.jar", "mode": "ro"}},
            ports={"8081/tcp": ("127.0.0.1", None)},
        )
        learning_url = f"http://127.0.0.1:{port(learning, 8081)}"
        wait_for(
            lambda: (
                httpx.get(learning_url + "/actuator/health/readiness").status_code
                == 200
            ),
            "learning HTTP readiness",
        )
        report_dsn = dsn.replace("report27_learning", "report27_report")
        os.environ.update(
            {
                "INTERNAL_TOKEN": token,
                "DATABASE_URL": report_dsn.replace(
                    "postgresql://", "postgresql+psycopg://"
                ),
                "LEARNING_URL": learning_url,
                "RABBITMQ_URL": f"amqp://verify:{password}@127.0.0.1:{port(rabbit, 5672)}/",
            }
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=REPORT, check=True
        )

        from app.clients.base import internal_client
        from app.clients.learning_client import LearningClient
        from app.database import create_db_engine, create_session_factory
        from app.generation.metrics import MetricsCalculator
        from app.generation.models import EvidenceLink, GenerateReport, ItemType
        from app.generation.presentation import from_result
        from app.generation.records import Period
        from app.generation.repository import ReportRepository
        from app.rendering.renderer import ReportRenderer
        from app.security import UserContext, bind_user_context, reset_user_context

        student = uuid4()
        period = Period(date(2026, 10, 19), date(2026, 10, 25))
        headers = {
            "X-Internal-Token": token,
            "X-User-Role": "SYSTEM",
            "X-Student-Scope": str(student),
        }
        http = cleanup.enter_context(
            httpx.Client(base_url=learning_url, headers=headers, timeout=30)
        )
        page_calls = []

        async def records():
            reset = bind_user_context(
                UserContext(None, "SYSTEM", frozenset({str(student)}), None)
            )
            try:

                async def capture(request):
                    if request.url.path.endswith(("/attempts", "/changes")):
                        page_calls.append(
                            (
                                request.url.path.rsplit("/", 1)[-1],
                                request.url.params["page"],
                            )
                        )

                async with internal_client(learning_url) as connection:
                    connection.event_hooks["request"].append(capture)
                    return await LearningClient(connection).records(student, period)
            finally:
                reset_user_context(reset)

        def get(name, **params):
            response = http.get(
                f"/internal/records/students/{student}/{name}",
                params={**period.payload(), **params},
            )
            response.raise_for_status()
            return response.json()

        assert (
            MetricsCalculator().calculate(asyncio.run(records())).state == "NO_RECORD"
        )
        passed("empty NO_RECORD through real learning HTTP")
        actor = uuid4()
        attempts = []

        def make(kind, content):
            mission, version, rubric = uuid4(), uuid4(), uuid4()
            db.execute(
                "INSERT INTO mission(id,code,status,demo_only,sort_order,created_by,created_at,updated_at) VALUES(%s,%s,'PUBLISHED',false,1,%s,now(),now())",
                (mission, str(mission), actor),
            )
            db.execute(
                "INSERT INTO mission_version(id,mission_id,version,title,subject,grade_min,grade_max,thinking_type,input_type,question,choices,created_by,created_at) VALUES(%s,%s,1,'Synthetic record','language',3,6,'ANALYZE',%s,'Synthetic question',%s,%s,now())",
                (
                    version,
                    mission,
                    kind,
                    Jsonb(
                        [
                            {"id": "c1", "label": "그래서 고른 것"},
                            {"id": "c2", "label": "다른 것"},
                        ]
                    ),
                    actor,
                ),
            )
            db.execute(
                "INSERT INTO rubric_version(id,mission_id,version,created_by,created_at) VALUES(%s,%s,1,%s,now())",
                (rubric, mission, actor),
            )
            db.execute(
                "UPDATE mission SET current_version_id=%s,current_rubric_version_id=%s WHERE id=%s",
                (version, rubric, mission),
            )
            response = http.post(
                f"/internal/missions/{mission}/attempts?grade=5",
                headers={"X-User-Role": "STUDENT"},
            )
            response.raise_for_status()
            attempt = UUID(response.json()["attemptId"])
            answer_ids = []
            followup = None
            for index in range(2):
                response = http.post(
                    f"/internal/attempts/{attempt}/answers",
                    headers={"X-User-Role": "STUDENT", "Idempotency-Key": str(uuid4())},
                    json={
                        "inputType": kind,
                        **content,
                        "followupId": str(followup) if followup else None,
                    },
                )
                response.raise_for_status()
                answer = UUID(response.json()["answerId"])
                answer_ids.append(answer)
                db.execute(
                    "UPDATE answer SET submitted_at=%s WHERE id=%s",
                    (f"2026-10-{18 if index == 0 else 20}T10:00:00+09:00", answer),
                )
                if index == 0:
                    judgment = db.execute(
                        "UPDATE judgment SET process_status='DONE',result='PARTIAL',method='LLM',trial=true WHERE answer_id=%s RETURNING id",
                        (answer,),
                    ).fetchone()[0]
                    followup = uuid4()
                    db.execute(
                        "INSERT INTO followup(id,attempt_id,judgment_id,type,question,source,leak_check_passed,created_at) VALUES(%s,%s,%s,'TELL_MORE','Synthetic question','LLM',true,'2026-10-19T10:00:00+09:00')",
                        (followup, attempt, judgment),
                    )
            attempts.append((attempt, answer_ids, rubric))
            return attempt, answer_ids

        inputs = [
            ("NARRATIVE", {"text": "왜냐하면 좋아요.🙂"}),
            (
                "SOLUTION_STEPS",
                {"steps": [" ", "2개와 3개를 더해요."], "finalAnswer": "5개"},
            ),
            (
                "ESSAY",
                {
                    "essay": {
                        "claim": "좋아요.",
                        "reasons": ["그늘 때문이에요.", "그래서 시원해요."],
                        "rebuttal": "따라서 심어요.",
                    }
                },
            ),
            ("CHOICE", {"choiceIds": ["c1"]}),
            ("ORDERING", {"choiceIds": ["c2", "c1"]}),
            (
                "CLASSIFICATION",
                {
                    "assignments": [
                        {"choiceId": "c1", "categoryId": "g1"},
                        {"choiceId": "c2", "categoryId": "g2"},
                    ]
                },
            ),
        ]
        for kind, content in inputs:
            make(kind, content)
            if len(attempts) in (1, 4, 5):
                state = MetricsCalculator().calculate(asyncio.run(records())).state
                assert state == ("OK" if len(attempts) == 5 else "INSUFFICIENT_SAMPLE")
        passed("actual submissions of all six input types; sample boundaries 1/4/5")
        # Schema-allowed legacy boundary: the advertised nullable followup must survive.
        db.execute(
            "UPDATE answer SET followup_id=NULL WHERE id=%s", (attempts[0][1][1],)
        )
        dataset = asyncio.run(records())
        result = MetricsCalculator().calculate(dataset)
        actual_changes = get("changes", size=100)
        supplied = {i["attemptId"]: i for i in actual_changes["items"]}
        for change in (i.payload for i in result.items if i.type == ItemType.CHANGE):
            actual = supplied[change["attemptId"]]
            assert change["counts"] == actual["counts"]
            assert (
                change["first"] == actual["first"]
                and change["revised"] == actual["revised"]
            )
        assert any(
            i.payload["followup"] is None
            for i in result.items
            if i.type == ItemType.CHANGE
        )
        assert dataset.attempts[0].answers[0].version == 1
        passed(
            "six-type counts equal actual learning counts; full display plaintext preserved; null followup"
        )
        for name in ("attempts", "thinking-types", "changes"):
            body = get(name, **({"size": 100} if name != "thinking-types" else {}))
            save(f"{name}.json", body)
            specification = yaml.safe_load(
                (ROOT / "contracts/openapi/learning-service.yaml").read_text(
                    encoding="utf-8"
                )
            )
            operation = specification["paths"][
                f"/records/students/{{studentId}}/{name}"
            ]["get"]
            schema = operation["responses"]["200"]["content"]["application/json"][
                "schema"
            ]
            Draft202012Validator(
                {**schema, "components": specification["components"]}
            ).validate(body)
        passed(
            "actual attempts/thinking-types/changes responses validate against checked-in OpenAPI"
        )

        async def evidence(links):
            reset = bind_user_context(
                UserContext(None, "SYSTEM", frozenset({str(student)}), None)
            )
            try:
                async with internal_client(learning_url) as connection:
                    return await LearningClient(connection).evidence(
                        student, tuple(links)
                    )
            finally:
                reset_user_context(reset)

        answer = dataset.attempts[0].answers[-1]
        link = EvidenceLink(dataset.attempts[0].id, answer.id, answer.version)
        missing = EvidenceLink(uuid4(), uuid4(), 1)
        values = asyncio.run(evidence([link, missing]))
        assert (
            values[0].text == answer.text
            and values[0].available
            and not values[1].available
        )
        response = http.get(
            "/internal/records/evidence",
            params={"answerIds": f"{answer.id},{missing.answer_id}"},
        )
        response.raise_for_status()
        save("evidence.json", response.json())
        assert (
            http.get(
                f"/internal/records/students/{student}/attempts",
                headers={"X-Student-Scope": str(uuid4())},
            ).status_code
            == 403
        )
        passed(
            "real evidence full text/version, mixed unavailable ID, and student scope 403"
        )

        engine = create_db_engine()
        cleanup.callback(engine.dispose)
        factory = create_session_factory(engine)
        repository = ReportRepository()
        command = GenerateReport(
            uuid4(), student, period.start, period.end, "SCHEDULE", False
        )
        with factory.begin() as session:
            report, _ = repository.get_or_create(session, command)
            repository.finish(session, report.id, result=result)
        rendered = ReportRenderer().render(from_result(report, result), "합성학생")
        from pypdf import PdfReader

        pdf = "".join(
            page.extract_text() for page in PdfReader(io.BytesIO(rendered["PDF"])).pages
        )
        for text in (rendered["HTML"].decode(), rendered["MD"].decode(), pdf):
            assert "None" not in text
        for kind, body in rendered.items():
            (output / f"report.{kind.lower()}").write_bytes(body)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            report_port = sock.getsockname()[1]
        log = cleanup.enter_context((output / "report-server.log").open("wb"))
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(report_port),
            ],
            cwd=REPORT,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        def stop_report():
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        cleanup.callback(stop_report)
        report_url = f"http://127.0.0.1:{report_port}"
        wait_for(
            lambda: httpx.get(report_url + "/health/live").status_code == 200,
            "report HTTP",
        )
        for premium in (False, True):
            response = httpx.get(
                f"{report_url}/internal/reports/{report.id}",
                headers={**headers, "X-Report-Narrative-Enabled": str(premium).lower()},
            )
            response.raise_for_status()
            body = response.json()
            assert body["childId"] == str(student)
            assert any(i["followup"] is None for i in body["changes"])
            save(f"report-detail-{premium}.json", body)
        passed(
            "report PostgreSQL persistence -> actual report HTTP (free/paid), HTML/MD/PDF rendering"
        )

        # Remaining fixtures use the same real submission API, so pagination includes
        # production DTO serialization and SQL ordering for both attempts and changes.
        while len(attempts) < 101:
            make("NARRATIVE", {"text": "합성 답변."})
        page_calls.clear()
        all_records = asyncio.run(records())
        assert len(all_records.attempts) == len(all_records.changes) == 101
        assert page_calls == [
            ("attempts", "0"),
            ("attempts", "1"),
            ("changes", "0"),
            ("changes", "1"),
        ]
        MetricsCalculator().calculate(all_records)
        passed("101 attempts and 101 changes across both real HTTP pages")
        db.execute(
            "INSERT INTO deleted_student(student_id,scope,event_id,deleted_at) VALUES(%s,'RECORDS',%s,now())",
            (student, uuid4()),
        )
        deleted = asyncio.run(records())
        assert not deleted.attempts and not deleted.changes
        assert MetricsCalculator().calculate(deleted).state == "NO_RECORD"
        assert not asyncio.run(evidence([link]))[0].available
        passed(
            "deleted_student marker -> NO_RECORD/empty lists/unavailable evidence (not deletion consumer)"
        )
        save(
            "result.json",
            {
                "passed": results,
                "count": len(results),
                "learningJar": jar.name,
                "scope": "real learning/report HTTP + isolated databases; AI/core scheduler/deletion consumer excluded",
            },
        )
    client.close()
    print(f"Completed {len(results)} checks; disposable services removed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/report27-live")
    verify(parser.parse_args().output.resolve())
