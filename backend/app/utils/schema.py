"""Lightweight SQLite column ensure for evolving local schema."""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.extensions import db


def ensure_sqlite_columns() -> None:
    """Add newly introduced columns when using SQLite without migrations."""
    bind = db.session.get_bind()
    if bind is None or bind.dialect.name != "sqlite":
        return

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    def add_column(table: str, column_sql: str) -> None:
        if table not in tables:
            return
        existing = {col["name"] for col in inspector.get_columns(table)}
        col_name = column_sql.split()[0]
        if col_name in existing:
            return
        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_sql}"))

    add_column("sync_runs", "trigger VARCHAR(32)")
    db.session.commit()
