import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    contact_id INTEGER NOT NULL UNIQUE,
    contact_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db() -> None:
    settings = get_settings()
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA)


@contextmanager
def _connect():
    settings = get_settings()
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def resolve_token(token: str) -> int | None:
    """Return the contact_id mapped to a token, or None if unknown."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT contact_id FROM tokens WHERE token = ?", (token,)
        ).fetchone()
        return row["contact_id"] if row else None


def find_token_for_contact(contact_id: int) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT token FROM tokens WHERE contact_id = ?", (contact_id,)
        ).fetchone()
        return row["token"] if row else None


def store_token(token: str, contact_id: int, contact_name: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO tokens (token, contact_id, contact_name)
            VALUES (?, ?, ?)
            ON CONFLICT(contact_id) DO UPDATE SET contact_name = excluded.contact_name
            """,
            (token, contact_id, contact_name),
        )


def list_tokens() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT token, contact_id, contact_name, created_at FROM tokens ORDER BY contact_name"
        ).fetchall()
