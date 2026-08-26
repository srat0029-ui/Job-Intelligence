"""Shared pytest fixtures.

Integration tests run against a real Postgres (a dedicated
`job_intelligence_test` database on the same server as local dev - see
docker-compose.yml), not sqlite/mocks, because the app genuinely depends on
Postgres-only features (JSONB, ARRAY columns, pgvector). Every test gets a
truncated database, so tests are isolated without needing a fresh container
per run.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import models  # noqa: F401 - registers all tables on Base.metadata
from app.db.base import Base

ADMIN_DATABASE_URL = "postgresql+psycopg://job_intel:job_intel@localhost:5432/job_intelligence"
TEST_DB_NAME = "job_intelligence_test"
TEST_DATABASE_URL = f"postgresql+psycopg://job_intel:job_intel@localhost:5432/{TEST_DB_NAME}"


def _ensure_test_database() -> None:
    engine = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    engine.dispose()


@pytest.fixture(scope="session")
def engine():
    _ensure_test_database()
    eng = create_engine(TEST_DATABASE_URL, future=True)
    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine) -> Generator[Session, None, None]:
    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    yield session
    session.rollback()
    session.close()
