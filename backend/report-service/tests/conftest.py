import os
import subprocess
import sys
from pathlib import Path

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
