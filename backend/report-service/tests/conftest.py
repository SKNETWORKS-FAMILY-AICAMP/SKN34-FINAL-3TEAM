import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.community.postgres import PostgresContainer

from app.database import create_db_engine

os.environ.setdefault("INTERNAL_TOKEN", "test-token")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:1/")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/x")


@pytest.fixture(scope="session")
def postgres():
    # Docker unavailable is a failure, not a silently skipped repository test.
    with PostgresContainer("postgres:17.11-alpine", driver="psycopg") as container:
        yield container


@pytest.fixture(scope="session")
def db_engine(postgres):
    url = postgres.get_connection_url()
    # Explicit test setup only; application startup never invokes migrations.
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DATABASE_URL": url},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        pytest.fail(f"Test DB migration failed:\n{result.stdout}\n{result.stderr}", pytrace=False)
    engine = create_db_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session_factory(db_engine):
    # Even a service's commit stays inside this test's outer rollback boundary.
    with db_engine.connect() as connection, connection.begin():
        factory = sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield factory
        finally:
            connection.rollback()


@pytest.fixture
def db_session(db_session_factory) -> Session:
    with db_session_factory() as session:
        yield session


@pytest.fixture
def report_student_id():
    return uuid4()


@pytest.fixture
def report_factory(db_engine, report_student_id):
    # Independent connections/real commits for concurrency and transaction visibility tests.
    from sqlalchemy import delete, select

    from app.generation.repository import report_item, report_item_evidence, weekly_report
    from app.outbox.repository import outbox_event

    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        with factory.begin() as session:
            reports = select(weekly_report.c.id).where(
                weekly_report.c.student_id == report_student_id
            )
            items = select(report_item.c.id).where(report_item.c.report_id.in_(reports))
            session.execute(
                delete(report_item_evidence).where(report_item_evidence.c.item_id.in_(items))
            )
            session.execute(delete(report_item).where(report_item.c.report_id.in_(reports)))
            session.execute(
                delete(outbox_event).where(outbox_event.c.subject == str(report_student_id))
            )
            session.execute(
                delete(weekly_report).where(weekly_report.c.student_id == report_student_id)
            )
