"""Small, transactional SQLite store for conversations and settings."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        with self._db:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, content TEXT NOT NULL,
                    tool_calls TEXT, tool_call_id TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, id);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def create_session(self, title: str = "新对话") -> str:
        sid, now = uuid.uuid4().hex, time.time()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?)", (sid, title, now, now)
            )
        return sid

    def sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._db.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            )]

    def rename_session(self, sid: str, title: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
                (title.strip()[:80] or "新对话", time.time(), sid),
            )

    def delete_session(self, sid: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM sessions WHERE id=?", (sid,))

    def add_message(self, sid: str, message: dict[str, Any]) -> int:
        role = message["role"]
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("invalid message role")
        content = message.get("content")
        if not isinstance(content, (str, list)) and content is not None:
            raise ValueError("invalid message content")
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO messages(session_id, role, content, tool_calls, tool_call_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (sid, role, json.dumps(content, ensure_ascii=False),
                 json.dumps(message.get("tool_calls"), ensure_ascii=False)
                 if message.get("tool_calls") is not None else None,
                 message.get("tool_call_id"), time.time()),
            )
            self._db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (time.time(), sid))
            return int(cursor.lastrowid)

    def messages(self, sid: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT role, content, tool_calls, tool_call_id FROM messages "
                "WHERE session_id=? ORDER BY id", (sid,)
            ).fetchall()
        result = []
        for row in rows:
            msg = {"role": row["role"], "content": json.loads(row["content"])}
            if row["tool_calls"]:
                msg["tool_calls"] = json.loads(row["tool_calls"])
            if row["tool_call_id"]:
                msg["tool_call_id"] = row["tool_call_id"]
            result.append(msg)
        return result

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value)
            )
