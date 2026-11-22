"""Database connection helper.

Default: the bundled SQLite file (data/smartmart.db).
Stage 2: set DATABASE_URL (env var or Streamlit secret) to a Postgres URL, e.g. Supabase.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

DEFAULT_SQLITE = Path(__file__).resolve().parent / "data" / "smartmart.db"


def sqlite_url(path: str | Path | None = None) -> str:
    return f"sqlite:///{Path(path or DEFAULT_SQLITE).resolve()}"


def resolve_url(url: str | None = None) -> str:
    url = url or os.getenv("DATABASE_URL") or sqlite_url()
    if url.startswith("postgres://"):  # some providers still hand out the old scheme
        url = "postgresql://" + url[len("postgres://"):]
    return url


def get_engine(url: str | None = None, must_exist: bool = True) -> Engine:
    """Return a SQLAlchemy engine. For SQLite, refuse to silently create an empty file."""
    parsed = make_url(resolve_url(url))
    if (
        parsed.get_backend_name() == "sqlite"
        and must_exist
        and parsed.database
        and parsed.database != ":memory:"
        and not Path(parsed.database).exists()
    ):
        raise FileNotFoundError(
            f"SQLite database not found: {parsed.database}. Build it with: python -m pipeline.run_all"
        )
    return create_engine(parsed, pool_pre_ping=True)
