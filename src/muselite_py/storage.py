"""Small, transactional SQLite store for conversations and settings."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
import re
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
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, prompt TEXT NOT NULL,
                    when_ms INTEGER NOT NULL, repeat_daily INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL,
                    last_triggered_at REAL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK(kind IN ('profile', 'semantic', 'episodic')),
                    key TEXT,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK(status IN ('pending', 'active', 'archived')),
                    confidence REAL NOT NULL DEFAULT 1.0,
                    importance INTEGER NOT NULL DEFAULT 50,
                    sensitive INTEGER NOT NULL DEFAULT 0,
                    source_session_id TEXT,
                    source_message_id INTEGER,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL,
                    supersedes_id TEXT
                );
                CREATE INDEX IF NOT EXISTS memories_status_expiry
                    ON memories(status, expires_at, updated_at);
                CREATE INDEX IF NOT EXISTS memories_key
                    ON memories(key, kind, status);
            """)
        self._fts5 = False
        try:
            with self._lock, self._db:
                self._db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts "
                    "USING fts5(memory_id UNINDEXED, key, content)"
                )
                self._db.execute("DELETE FROM memories_fts")
                self._db.execute(
                    "INSERT INTO memories_fts(memory_id, key, content) "
                    "SELECT id, coalesce(key, ''), content FROM memories"
                )
            self._fts5 = True
        except sqlite3.DatabaseError:
            # Some vendor Android SQLite builds omit FTS5. Search has a LIKE fallback.
            self._fts5 = False

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

    def all_conversation_messages(self) -> list[dict[str, Any]]:
        """Return all historical messages with source metadata for explicit memory writes."""
        with self._lock:
            rows = self._db.execute(
                "SELECT m.id, m.session_id, m.role, m.content, m.created_at, "
                "s.title AS session_title FROM messages m "
                "JOIN sessions s ON s.id=m.session_id ORDER BY m.id"
            ).fetchall()
        result = []
        for row in rows:
            result.append({
                "id": row["id"], "session_id": row["session_id"],
                "session_title": row["session_title"], "role": row["role"],
                "content": json.loads(row["content"]), "created_at": row["created_at"],
            })
        return result

    def _memory_row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["sensitive"] = bool(item.get("sensitive"))
        return item

    def memory(self, memory_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return self._memory_row(row)

    def _sync_memory_fts(self, memory_id: str, key: str | None, content: str) -> None:
        if not self._fts5:
            return
        self._db.execute("DELETE FROM memories_fts WHERE memory_id=?", (memory_id,))
        self._db.execute(
            "INSERT INTO memories_fts(memory_id, key, content) VALUES (?, ?, ?)",
            (memory_id, key or "", content),
        )

    def write_memory(self, *, kind: str, content: str, key: str | None = None,
                     status: str = "active", confidence: float = 1.0,
                     importance: int = 50, sensitive: bool = False,
                     source_session_id: str | None = None,
                     source_message_id: int | None = None,
                     expires_at: float | None = None,
                     supersedes_id: str | None = None) -> dict[str, Any]:
        kind, status = str(kind).strip().lower(), str(status).strip().lower()
        content, key = str(content).strip(), (str(key).strip() or None) if key else None
        if kind not in {"profile", "semantic", "episodic"}:
            raise ValueError("记忆类型必须是 profile、semantic 或 episodic")
        if status not in {"pending", "active", "archived"}:
            raise ValueError("无效的记忆状态")
        if not content or len(content) > 500:
            raise ValueError("记忆内容不能为空且不能超过 500 字")
        confidence = max(0.0, min(1.0, float(confidence)))
        importance = max(0, min(100, int(importance)))
        now = time.time()
        with self._lock, self._db:
            duplicate = self._db.execute(
                "SELECT * FROM memories WHERE kind=? AND coalesce(key, '')=coalesce(?, '') "
                "AND content=? AND status != 'archived' LIMIT 1",
                (kind, key, content),
            ).fetchone()
            if duplicate is not None:
                return self._memory_row(duplicate)  # type: ignore[return-value]
            memory_id = uuid.uuid4().hex
            self._db.execute(
                "INSERT INTO memories(id, kind, key, content, status, confidence, importance, "
                "sensitive, source_session_id, source_message_id, created_at, updated_at, "
                "expires_at, supersedes_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (memory_id, kind, key, content, status, confidence, importance, int(sensitive),
                 source_session_id, source_message_id, now, now, expires_at, supersedes_id),
            )
            self._sync_memory_fts(memory_id, key, content)
            row = self._db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return self._memory_row(row)  # type: ignore[return-value]

    def list_memories(self, *, status: str | None = None,
                      kind: str | None = None, include_expired: bool = False) -> list[dict[str, Any]]:
        where, values = ["1=1"], []
        if status:
            where.append("status=?"); values.append(status)
        if kind:
            where.append("kind=?"); values.append(kind)
        if not include_expired:
            where.append("(expires_at IS NULL OR expires_at > ?)"); values.append(time.time())
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM memories WHERE " + " AND ".join(where) +
                " ORDER BY updated_at DESC", values).fetchall()
        return [self._memory_row(row) for row in rows]  # type: ignore[list-item]

    def search_memories(self, query: str = "", *, kinds: list[str] | None = None,
                        limit: int = 12) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        limit = max(1, min(50, int(limit)))
        now = time.time()
        kind_filter = set(kinds or {"profile", "semantic", "episodic"})
        kind_filter &= {"profile", "semantic", "episodic"}
        if not kind_filter:
            return []
        terms = []
        for part in re.findall(r"[\u3400-\u9fff]{2,}|[A-Za-z0-9_.-]{2,}", query):
            part = part.casefold()
            terms.append(part)
            if re.fullmatch(r"[\u3400-\u9fff]+", part) and len(part) > 4:
                terms.extend(part[index:index + 2] for index in range(len(part) - 1))
        aliases = {
            "中文": {"language"}, "简体中文": {"language"}, "语言": {"language"},
            "简洁": {"response_style"}, "回答风格": {"response_style"},
            "称呼": {"name"}, "名字": {"name"},
        }
        exact_keys = set()
        for phrase, keys in aliases.items():
            if phrase in query.casefold():
                exact_keys.update(keys)
        candidates: dict[str, tuple[dict[str, Any], float]] = {}

        def add(row: sqlite3.Row, score: float) -> None:
            item = self._memory_row(row)
            if item is None or item["kind"] not in kind_filter:
                return
            if item["status"] != "active" or (item["expires_at"] is not None and item["expires_at"] <= now):
                return
            current = candidates.get(item["id"])
            if current is None or score > current[1]:
                candidates[item["id"]] = (item, score)

        with self._lock:
            if exact_keys:
                placeholders = ",".join("?" for _ in exact_keys)
                rows = self._db.execute(
                    "SELECT * FROM memories WHERE status='active' AND (expires_at IS NULL OR expires_at > ?) "
                    f"AND key IN ({placeholders})", [now, *exact_keys]).fetchall()
                for row in rows:
                    add(row, 130.0)
            if query:
                rows = self._db.execute(
                    "SELECT * FROM memories WHERE status='active' AND (expires_at IS NULL OR expires_at > ?) "
                    "AND instr(lower(content), lower(?)) > 0", (now, query)).fetchall()
                for row in rows:
                    add(row, 115.0)
            if self._fts5 and terms:
                fts_query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
                try:
                    rows = self._db.execute(
                        "SELECT m.*, bm25(memories_fts) AS bm "
                        "FROM memories_fts JOIN memories m ON m.id=memories_fts.memory_id "
                        "WHERE memories_fts MATCH ? AND m.status='active' "
                        "AND (m.expires_at IS NULL OR m.expires_at > ?) "
                        "LIMIT 100", (fts_query, now)).fetchall()
                    for row in rows:
                        add(row, 80.0 + max(0.0, min(30.0, -float(row["bm"]))))
                except sqlite3.DatabaseError:
                    pass
            if query:
                # Substring matching supplements FTS5 for Chinese text, where the
                # bundled tokenizer may not split words as expected.
                for term in terms:
                    rows = self._db.execute(
                        "SELECT * FROM memories WHERE status='active' AND (expires_at IS NULL OR expires_at > ?) "
                        "AND (instr(lower(content), lower(?)) > 0 OR instr(lower(coalesce(key,'')), lower(?)) > 0)",
                        (now, term, term)).fetchall()
                    for row in rows:
                        add(row, 75.0)
            # Stable profile facts are useful context even when the message has no matching term.
            rows = self._db.execute(
                "SELECT * FROM memories WHERE kind='profile' AND status='active' "
                "AND (expires_at IS NULL OR expires_at > ?) ORDER BY importance DESC, updated_at DESC LIMIT 4",
                (now,)).fetchall()
            for row in rows:
                add(row, 35.0)

        def sort_key(pair: tuple[dict[str, Any], float]):
            item, score = pair
            age_days = max(0.0, (now - float(item["updated_at"])) / 86400.0)
            recency = max(0.0, 10.0 - min(10.0, age_days / 7.0))
            kind_weight = {"profile": 20.0, "semantic": 10.0, "episodic": 0.0}[item["kind"]]
            return score + kind_weight + int(item["importance"]) * 0.2 + recency

        ranked = sorted(candidates.values(), key=sort_key, reverse=True)
        return [item for item, _score in ranked[:limit]]

    def update_memory(self, memory_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {"kind", "key", "content", "status", "confidence", "importance", "sensitive", "expires_at"}
        changes = {key: value for key, value in changes.items() if key in allowed}
        if not changes:
            return self.memory(memory_id)
        if "content" in changes:
            changes["content"] = str(changes["content"]).strip()
            if not changes["content"] or len(changes["content"]) > 500:
                raise ValueError("记忆内容不能为空且不能超过 500 字")
        changes["updated_at"] = time.time()
        assignments = ", ".join(f"{key}=?" for key in changes)
        with self._lock, self._db:
            self._db.execute(f"UPDATE memories SET {assignments} WHERE id=?",
                             [*changes.values(), memory_id])
            row = self._db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if row is not None:
                self._sync_memory_fts(memory_id, row["key"], row["content"])
        return self._memory_row(row)

    def accept_memory_candidate(self, memory_id: str) -> dict[str, Any] | None:
        with self._lock, self._db:
            row = self._db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if row is None:
                return None
            if row["key"] and row["kind"] in {"profile", "semantic"}:
                self._db.execute(
                    "UPDATE memories SET status='archived', updated_at=? WHERE kind=? AND key=? "
                    "AND status='active' AND id != ?", (time.time(), row["kind"], row["key"], memory_id))
            self._db.execute("UPDATE memories SET status='active', updated_at=? WHERE id=?",
                             (time.time(), memory_id))
            row = self._db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return self._memory_row(row)

    def delete_memory(self, memory_id: str) -> bool:
        with self._lock, self._db:
            cursor = self._db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            if self._fts5:
                self._db.execute("DELETE FROM memories_fts WHERE memory_id=?", (memory_id,))
        return cursor.rowcount > 0

    def clear_memories(self) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM memories")
            if self._fts5:
                self._db.execute("DELETE FROM memories_fts")

    def export_memories(self, *, markdown: bool = False) -> str:
        records = self.list_memories(status="active", include_expired=False)
        if not markdown:
            return json.dumps(records, ensure_ascii=False, indent=2)
        lines = ["# MuseLite 长期记忆", ""]
        for item in records:
            lines += [f"## {item['kind']} / {item.get('key') or '未分类'}",
                      item["content"], ""]
        return "\n".join(lines)

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

    def create_scheduled_task(self, name: str, prompt: str, when_ms: int,
                              repeat_daily: bool) -> dict[str, Any]:
        name, prompt = name.strip(), prompt.strip()
        if not name or not prompt:
            raise ValueError("请填写任务名称和任务要求")
        if not repeat_daily and int(when_ms) <= int(time.time() * 1000):
            raise ValueError("请选择未来的时间")
        task_id = uuid.uuid4().hex
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO scheduled_tasks VALUES (?, ?, ?, ?, ?, 1, ?, NULL)",
                (task_id, name[:80], prompt, int(when_ms), int(repeat_daily), time.time()),
            )
        return self.scheduled_task(task_id)

    def scheduled_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM scheduled_tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row) if row else None

    def scheduled_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._db.execute(
                "SELECT * FROM scheduled_tasks ORDER BY created_at DESC"
            )]

    def set_scheduled_task_enabled(self, task_id: str, enabled: bool) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE scheduled_tasks SET enabled=? WHERE id=?",
                             (int(enabled), task_id))

    def mark_scheduled_task_triggered(self, task_id: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE scheduled_tasks SET last_triggered_at=?, "
                "enabled=CASE WHEN repeat_daily=1 THEN enabled ELSE 0 END WHERE id=?",
                (time.time(), task_id),
            )

    def delete_scheduled_task(self, task_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM scheduled_tasks WHERE id=?", (task_id,))
