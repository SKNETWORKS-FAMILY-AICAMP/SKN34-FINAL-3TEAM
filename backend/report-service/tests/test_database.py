from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, DateTime, MetaData, String, Table, inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError

from app.bootstrap import create_app
from app.config import get_settings
from app.database import create_db_engine, create_session_factory, transaction

# Query definitions for existing migrated tables; no create_all and no production Repository.
metadata = MetaData()
outbox = Table(
    "outbox_event",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("event_type", String, nullable=False),
    Column("routing_key", String, nullable=False),
    Column("subject", String, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
)


def event():
    return {
        "id": uuid4(),
        "event_type": "test.synthetic",
        "routing_key": "test.synthetic",
        "subject": "synthetic-test-only",
        "payload": {"message": "직접 만든 테스트", "nested": {"values": [1, True, None]}},
        "created_at": datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone(timedelta(hours=9))),
        "published_at": None,
    }


def test_jsonb_uuid_and_timezone_aware_timestamp_round_trip(db_session):
    row = event()
    db_session.execute(outbox.insert().values(**row))
    actual = db_session.execute(select(outbox).where(outbox.c.id == row["id"])).mappings().one()
    assert actual["id"] == row["id"]
    assert actual["payload"] == row["payload"]
    assert actual["created_at"].astimezone(UTC) == row["created_at"].astimezone(UTC)
    assert actual["published_at"] is None
    assert db_session.scalar(text("SELECT version_num FROM alembic_version"))


def test_transaction_commits_and_closes_session(db_session_factory):
    row = event()
    with transaction(db_session_factory) as session:
        session.execute(outbox.insert().values(**row))
    assert not session.in_transaction()
    with db_session_factory() as observer:
        assert observer.scalar(select(outbox.c.id).where(outbox.c.id == row["id"])) == row["id"]


def test_transaction_rolls_back_all_writes_and_propagates_error(db_session_factory):
    row = event()
    with pytest.raises(IntegrityError) as error:
        with transaction(db_session_factory) as session:
            session.execute(outbox.insert().values(**row))
            session.execute(outbox.insert().values(**row))
    assert error.value.orig.sqlstate == "23505"
    assert not session.in_transaction()
    with db_session_factory() as observer:
        assert observer.scalar(select(outbox.c.id).where(outbox.c.id == row["id"])) is None


def test_transaction_rolls_back_on_application_error(db_session_factory):
    row = event()
    with pytest.raises(ValueError, match="synthetic failure"):
        with transaction(db_session_factory) as session:
            session.execute(outbox.insert().values(**row))
            raise ValueError("synthetic failure")
    with db_session_factory() as observer:
        assert observer.scalar(select(outbox.c.id).where(outbox.c.id == row["id"])) is None


def test_factory_uses_independent_sessions(db_engine):
    factory = create_session_factory(db_engine)
    with factory() as first, factory() as second:
        assert first is not second
        assert first.bind is db_engine


def test_application_startup_does_not_migrate_empty_database(postgres, monkeypatch):
    # A separate, empty DB on the disposable server, independent of db_engine's migration.
    admin = create_db_engine(postgres.get_connection_url())
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("CREATE DATABASE startup_probe"))
    url = admin.url.set(database="startup_probe")
    admin.dispose()
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            assert client.get("/health/live").status_code == 200
            assert inspect(client.app.state.engine).get_table_names() == []
            with transaction(client.app.state.session_factory) as session:
                assert session.scalar(text("SELECT 1")) == 1
            assert inspect(client.app.state.engine).get_table_names() == []
    finally:
        get_settings.cache_clear()


def test_ordinary_postgresql_url_uses_psycopg3():
    engine = create_db_engine("postgresql://u:p@127.0.0.1:1/test")
    try:
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()
