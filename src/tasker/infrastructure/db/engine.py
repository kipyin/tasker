"""SQLite engine factory and schema creation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

import tasker.infrastructure.db.models  # noqa: F401 — register SQLModel table metadata


def _migrate_sqlite_schema(engine: Engine) -> None:
    """Apply additive ALTERs for databases created before new columns existed."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    tables = set(insp.get_table_names())

    if "message_refs" in tables:
        existing = {c["name"] for c in insp.get_columns("message_refs")}
        additions: list[tuple[str, str]] = [
            ("subject", "TEXT"),
            ("sender", "TEXT"),
            ("recipients_to", "TEXT"),
            ("recipients_cc", "TEXT"),
            ("recipients_bcc", "TEXT"),
            ("body_text", "TEXT"),
            ("attachment_names_json", "TEXT"),
            ("outlook_entry_id", "TEXT"),
            ("outlook_store_id", "TEXT"),
        ]
        with engine.begin() as conn:
            for col_name, sql_type in additions:
                if col_name not in existing:
                    conn.execute(
                        text(
                            f"ALTER TABLE message_refs ADD COLUMN {col_name} {sql_type}"
                        )
                    )

    if "tasks" in tables:
        task_cols = {c["name"] for c in insp.get_columns("tasks")}
        if "attachment_routes_json" not in task_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE tasks ADD COLUMN attachment_routes_json TEXT")
                )


def make_sqlite_engine(database_path: str) -> Engine:
    """Create a SQLAlchemy engine for a SQLite file path (no `sqlite:///` prefix)."""
    url = f"sqlite:///{database_path}"
    return create_engine(
        url,
        connect_args={"check_same_thread": False},
    )


def init_db(engine: Engine) -> None:
    """Create all tables if they do not exist."""
    SQLModel.metadata.create_all(engine)
    _migrate_sqlite_schema(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
