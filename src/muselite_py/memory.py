"""Explicit long-term memory policy and history-backed writer."""

from __future__ import annotations

import re
import time
from typing import Any

from .storage import Store


_EXPLICIT_MARKERS = (
    "记住", "记下", "保存", "存下", "别忘了", "不要忘记", "请勿忘记", "长期记忆",
    "remember", "save this", "save that", "don't forget", "do not forget",
)
_SENSITIVE_PATTERNS = (
    r"api[_ -]?key", r"token", r"password", r"密码", r"口令", r"密钥",
    r"信用卡", r"银行卡", r"身份证", r"病历", r"健康", r"social security",
)


def has_explicit_memory_intent(text: str) -> bool:
    """Return whether the current user request explicitly asks to remember something."""
    lowered = str(text or "").casefold()
    return any(marker.casefold() in lowered for marker in _EXPLICIT_MARKERS)


def looks_sensitive(text: str) -> bool:
    lowered = str(text or "").casefold()
    return any(re.search(pattern, lowered) for pattern in _SENSITIVE_PATTERNS)


def _tokens(text: str) -> set[str]:
    # Keep CJK runs and ASCII identifiers; this is only for source attribution,
    # not the user-facing search ranking.
    return {part.casefold() for part in re.findall(r"[\u3400-\u9fff]{2,}|[A-Za-z0-9_.-]{2,}", text)}


class MemoryWriter:
    """Write only explicit requests, using all stored conversations as evidence."""

    def __init__(self, store: Store):
        self.store = store

    def write_from_history(self, *, request: str, content: str, kind: str = "semantic",
                           key: str | None = None, source_session_id: str | None = None,
                           source_message_id: int | None = None,
                           expires_at: float | None = None,
                           confidence: float = 1.0, importance: int = 50) -> dict[str, Any]:
        if not has_explicit_memory_intent(request):
            raise ValueError("只有明确要求记住或保存时才能写入长期记忆")
        content = str(content or "").strip()
        if not content:
            raise ValueError("记忆内容不能为空")
        history = self.store.all_conversation_messages()
        content_tokens = _tokens(content)
        evidence = []
        for message in history:
            body = message.get("content")
            if not isinstance(body, str):
                continue
            body_tokens = _tokens(body)
            overlap = len(content_tokens & body_tokens)
            if overlap:
                evidence.append((overlap, message))
        evidence.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
        source = evidence[0][1] if evidence else None
        if source is not None:
            source_session_id = source["session_id"]
            source_message_id = source["id"]
        # Explicit requests may contain sensitive values, but they remain pending
        # until the user approves them from the memory manager.
        sensitive = looks_sensitive(content)
        status = "pending" if sensitive else "active"
        supersedes_id = None
        if key and kind in {"profile", "semantic"}:
            existing = [item for item in self.store.list_memories(
                status="active", kind=kind, include_expired=True)
                        if item.get("key") == key and item.get("content") != content]
            if existing:
                status = "pending"
                supersedes_id = existing[0]["id"]
        # Episodic notes are intentionally short-lived unless the caller supplies
        # a custom expiration.
        if kind == "episodic" and expires_at is None:
            expires_at = time.time() + 30 * 86400
        return self.store.write_memory(
            kind=kind, key=key, content=content, status=status,
            confidence=confidence, importance=importance, sensitive=sensitive,
            source_session_id=source_session_id, source_message_id=source_message_id,
            expires_at=expires_at, supersedes_id=supersedes_id,
        )
