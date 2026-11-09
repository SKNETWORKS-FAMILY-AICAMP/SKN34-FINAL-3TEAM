"""Old weekly rows survive the nullable/backfill/finalize migration unchanged."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.database import create_db_engine


def test_backfill_keeps_old_report_and_guard_and_downgrade_refuses_daily_data(postgres):
    database = "period_" + uuid4().hex
    control = create_db_engine(postgres.get_connection_url())
    url = make_url(postgres.get_connection_url()).set(database=database)
    engine = None

    def migrate(target, direction="upgrade", success=True):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "alembic", direction, target],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)},
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert (result.returncode == 0) is success, result.stderr

    try:
        with control.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'CREATE DATABASE "{database}"'))
        migrate("20261102_05")
        engine = create_db_engine(url)
        identifier, job, student = uuid4(), uuid4(), uuid4()
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO weekly_report(id,job_id,student_id,period_from,period_to,
                    revision,status,state,narrative,created_at)
                VALUES(:id,:job,:student,'2026-11-02','2026-11-08',3,'COMPLETED','OK',
                    '{"text":"preserve"}',now())
            """),
                {"id": identifier, "job": job, "student": student},
            )
            conn.execute(
                text("""
                INSERT INTO report_job_guard(job_id,student_id,period_from,period_to,
                    failure_reason,created_at)
                VALUES(:job,:student,'2026-11-02','2026-11-08','REPORT_NOT_CREATED',now())
            """),
                {"job": uuid4(), "student": student},
            )
        migrate("20261109_06")
        # A previous worker can still write during the nullable prepare phase.
        # Finalize must backfill these late rows as well, without a SQL default.
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO report_job_guard(job_id,student_id,period_from,period_to,
                    failure_reason,created_at)
                VALUES(:job,:student,'2026-11-02','2026-11-08','REPORT_NOT_CREATED',now())
                """),
                {"job": uuid4(), "student": student},
            )
            assert (
                conn.scalar(text("SELECT count(*) FROM report_job_guard WHERE period_type IS NULL"))
                == 1
            )
        migrate("head")
        with engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM weekly_report")).mappings().one()
            assert row["id"] == identifier and row["revision"] == 3
            assert row["narrative"] == {"text": "preserve"} and row["period_type"] == "WEEKLY"
            assert (
                conn.scalar(
                    text("SELECT count(*) FROM report_job_guard WHERE period_type = 'WEEKLY'")
                )
                == 2
            )
            conn.execute(
                text("""
                INSERT INTO weekly_report(id,job_id,student_id,period_from,period_to,
                    revision,status,period_type,created_at)
                VALUES(:id,:job,:student,'2026-11-02','2026-11-02',1,'RUNNING','DAILY',now())
            """),
                {"id": uuid4(), "job": uuid4(), "student": student},
            )
        migrate("20261109_06", "downgrade", success=False)
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM weekly_report")) == 2
    finally:
        if engine is not None:
            engine.dispose()
        with control.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        control.dispose()
