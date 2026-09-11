"""SQLite 연결과 chat_history / drawings 테이블."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BACKEND_DIR.parent


def db_path() -> Path:
    raw = os.getenv("SQLITE_PATH", "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = _ROOT_DIR / path
    else:
        path = _BACKEND_DIR / "data" / "app.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              input TEXT NOT NULL,
              response TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drawings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              history_id INTEGER,
              spec_json TEXT NOT NULL,
              png BLOB NOT NULL,
              title TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (history_id) REFERENCES chat_history(id)
            )
            """
        )
        conn.commit()


def save_chat(input_text: str, ai_response: str) -> tuple[int, str]:
    created_at = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO chat_history (input, response, created_at) VALUES (?, ?, ?)",
            (input_text, ai_response, created_at),
        )
        conn.commit()
        return int(cursor.lastrowid), created_at


def save_drawing(spec_json: str, png: bytes, history_id: int | None = None, title: str | None = None) -> int:
    created_at = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO drawings (history_id, spec_json, png, title, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (history_id, spec_json, png, title, created_at),
        )
        conn.commit()
        return int(cursor.lastrowid)
