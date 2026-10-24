from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.config import DB_PATH, ensure_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_ci
    ON users (LOWER(username));

CREATE TABLE IF NOT EXISTS subjects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_subjects_user_slug
    ON subjects (user_id, slug);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    size_bytes INTEGER,
    sha256 TEXT,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    doc_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    ensure_data_dir()
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def _row(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    found = cursor.fetchone()
    return dict(found) if found else None


# --- users ---

def create_user(
    username: str,
    password_hash: str,
    display_name: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    user_id = new_id()
    created = now_iso()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users (id, username, display_name, password_hash, created_at, failed_logins)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (user_id, username, display_name or username, password_hash, created),
        )
    return get_user_by_id(user_id, db_path=db_path)  # type: ignore[return-value]


def get_user_by_username(username: str, db_path: Path | None = None) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
            (username,),
        )
        return _row(cur)


def get_user_by_id(user_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return _row(cur)


def update_login_failure(
    user_id: str,
    failed_logins: int,
    locked_until: str | None,
    db_path: Path | None = None,
) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
            (failed_logins, locked_until, user_id),
        )


def reset_login_failures(user_id: str, db_path: Path | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?",
            (user_id,),
        )


# --- subjects ---

def create_subject(
    user_id: str,
    name: str,
    slug: str,
    db_path: Path | None = None,
) -> dict[str, Any]:
    subject_id = new_id()
    created = now_iso()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO subjects (id, user_id, slug, name, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (subject_id, user_id, slug, name, created),
        )
    found = get_subject(user_id, subject_id, db_path=db_path)
    if found is None:
        raise RuntimeError("Failed to load created subject")
    return found


def subject_slug_exists(user_id: str, slug: str, db_path: Path | None = None) -> bool:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "SELECT 1 FROM subjects WHERE user_id = ? AND slug = ?",
            (user_id, slug),
        )
        return cur.fetchone() is not None


def get_subject(user_id: str, subject_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM subjects WHERE id = ? AND user_id = ?",
            (subject_id, user_id),
        )
        return _row(cur)


def list_subjects(user_id: str, db_path: Path | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT s.*,
                   (
                     SELECT COUNT(*) FROM documents d
                     WHERE d.subject_id = s.id AND d.user_id = s.user_id AND d.status = 'ready'
                   ) AS ready_count
            FROM subjects s
            WHERE s.user_id = ?
            ORDER BY s.created_at ASC
            """,
            (user_id,),
        )
        return _rows(cur)


def rename_subject(
    user_id: str,
    subject_id: str,
    name: str,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE subjects SET name = ? WHERE id = ? AND user_id = ?",
            (name, subject_id, user_id),
        )
    return get_subject(user_id, subject_id, db_path=db_path)


# --- documents ---

def insert_document(
    *,
    doc_id: str,
    user_id: str,
    subject_id: str,
    filename: str,
    size_bytes: int | None,
    sha256: str | None,
    status: str,
    error: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    created = now_iso()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO documents (
                id, user_id, subject_id, filename, size_bytes, sha256,
                status, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                user_id,
                subject_id,
                filename,
                size_bytes,
                sha256,
                status,
                error,
                created,
                created,
            ),
        )
    found = get_document(user_id, doc_id, db_path=db_path)
    if found is None:
        raise RuntimeError("Failed to load created document")
    return found


def get_document(user_id: str, doc_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        )
        return _row(cur)


def find_document_by_hash(
    user_id: str,
    subject_id: str,
    sha256: str,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT * FROM documents
            WHERE user_id = ? AND subject_id = ? AND sha256 = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, subject_id, sha256),
        )
        return _row(cur)


def list_documents(user_id: str, subject_id: str, db_path: Path | None = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT * FROM documents
            WHERE user_id = ? AND subject_id = ?
            ORDER BY created_at DESC
            """,
            (user_id, subject_id),
        )
        return _rows(cur)


def list_processing_documents(
    user_id: str, subject_id: str, db_path: Path | None = None
) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT * FROM documents
            WHERE user_id = ? AND subject_id = ? AND status = 'processing'
            """,
            (user_id, subject_id),
        )
        return _rows(cur)


def count_ready_documents(
    user_id: str, subject_id: str, db_path: Path | None = None
) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT COUNT(*) AS n FROM documents
            WHERE user_id = ? AND subject_id = ? AND status = 'ready'
            """,
            (user_id, subject_id),
        )
        row = cur.fetchone()
        return int(row["n"]) if row else 0


def list_ready_documents(
    user_id: str, subject_id: str, db_path: Path | None = None
) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT * FROM documents
            WHERE user_id = ? AND subject_id = ? AND status = 'ready'
            ORDER BY filename ASC
            """,
            (user_id, subject_id),
        )
        return _rows(cur)


def update_document_status(
    user_id: str,
    doc_id: str,
    status: str,
    error: str | None = None,
    db_path: Path | None = None,
) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE documents
            SET status = ?, error = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (status, error, now_iso(), doc_id, user_id),
        )


# --- messages ---

def insert_message(
    *,
    user_id: str,
    subject_id: str,
    role: str,
    content: str,
    doc_id: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    created = now_iso()
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO messages (user_id, subject_id, doc_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, subject_id, doc_id, role, content, created),
        )
        msg_id = cur.lastrowid
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM messages WHERE id = ? AND user_id = ?",
            (msg_id, user_id),
        )
        row = _row(cur)
        if row is None:
            raise RuntimeError("Failed to load created message")
        return row


def list_messages(
    user_id: str, subject_id: str, db_path: Path | None = None
) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT * FROM messages
            WHERE user_id = ? AND subject_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (user_id, subject_id),
        )
        return _rows(cur)


def clear_messages(user_id: str, subject_id: str, db_path: Path | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "DELETE FROM messages WHERE user_id = ? AND subject_id = ?",
            (user_id, subject_id),
        )
