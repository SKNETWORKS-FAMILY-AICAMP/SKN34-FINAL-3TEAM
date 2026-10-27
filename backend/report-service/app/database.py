"""Shared DB infrastructure; application services own short transaction scopes.

No migration, reflection or create_all is performed when constructing these objects.
Repositories receive a Session and never commit/rollback it themselves.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

DB_CONNECT_TIMEOUT_SECONDS = 3


def create_db_engine(database_url: str | URL | None = None) -> Engine:
    url = make_url(database_url if database_url is not None else get_settings().database_url)
    # Keep the installed psycopg 3 driver for ordinary PostgreSQL URLs as well.
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use postgresql or postgresql+psycopg")
    return create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit on success, rollback on error and always close the per-operation session."""
    with factory.begin() as session:
        yield session
