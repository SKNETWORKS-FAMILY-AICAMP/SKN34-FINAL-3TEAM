"""기존 v3 Outbox 데이터의 upgrade/downgrade, 기본값 없는 카운터 초기화 검증."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.database import create_db_engine


def test_upgrade_and_downgrade_preserve_existing_pending_and_published_envelopes(postgres):
    root = Path(__file__).resolve().parents[1]
    database = "migration_" + uuid4().hex
    control = create_db_engine(postgres.get_connection_url())
    url = make_url(postgres.get_connection_url()).set(database=database)
    engine = None

    def migrate(target, direction="upgrade"):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=root,
            env={**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)},
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert result.returncode == 0, result.stderr

    try:
        with control.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'CREATE DATABASE "{database}"'))
        migrate("20261029_03")
        engine = create_db_engine(url)
        ids = [uuid4(), uuid4()]
        with engine.begin() as conn:
            for index, event_id in enumerate(ids):
                conn.execute(
                    text("""
                    INSERT INTO outbox_event
                        (id,event_type,routing_key,subject,payload,created_at,published_at)
                    VALUES(:id,'report.started','report.started',:subject,
                           CAST(:body AS jsonb),now(),
                           CASE WHEN :published THEN now() ELSE NULL END)
                """),
                    {
                        "id": event_id,
                        "subject": str(uuid4()),
                        "body": json.dumps({"synthetic": index}),
                        "published": index == 1,
                    },
                )
        migrate("head")
        with engine.connect() as conn:
            data = conn.execute(
                text(
                    "SELECT id,payload,published_at,failure_count,manual_retry_count "
                    "FROM outbox_event ORDER BY created_at,id"
                )
            ).all()
            assert {r[0] for r in data} == set(ids)
            assert all(r[3:] == (0, 0) for r in data)
            assert sum(r[2] is not None for r in data) == 1
            assert (
                conn.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name='outbox_event' AND column_default IS NOT NULL"
                    )
                )
                == 0
            )
        migrate("20261029_03", "downgrade")
        with engine.connect() as conn:
            restored = conn.execute(
                text("SELECT id,payload,published_at FROM outbox_event ORDER BY created_at,id")
            ).all()
            assert restored == [r[:3] for r in data]
        migrate("head")
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM outbox_event")) == 2
    finally:
        if engine is not None:
            engine.dispose()
        with control.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        control.dispose()
