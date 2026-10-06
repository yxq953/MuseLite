"""Agent tool schemas and implementations."""

from __future__ import annotations

import json
import threading
from typing import Any

from .browser import ACTIONS, BrowserController
from .phone import ACTIONS as PHONE_ACTIONS, PhoneController
from .sandbox import ProotSandbox, SandboxError
from .memory import MemoryWriter
from .storage import Store


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }}


TOOL_SCHEMAS = [
    _schema("shell_execute", "Run a command in the Alpine Linux sandbox.", {
        "command": {"type": "string"}, "timeout": {"type": "integer"},
    }, ["command"]),
    _schema("file_read", "Read a UTF-8 file in the Linux sandbox.", {
        "path": {"type": "string"},
    }, ["path"]),
    _schema("file_write", "Create or replace a UTF-8 file in the Linux sandbox.", {
        "path": {"type": "string"}, "content": {"type": "string"},
    }, ["path", "content"]),
    _schema("file_edit", "Replace one exact string in a UTF-8 sandbox file.", {
        "path": {"type": "string"}, "old_text": {"type": "string"},
        "new_text": {"type": "string"},
    }, ["path", "old_text", "new_text"]),
    _schema("memory_write", "Save a persistent memory only when the user explicitly asked you to remember it.", {
        "content": {"type": "string"},
        "kind": {"type": "string", "enum": ["profile", "semantic", "episodic"]},
        "key": {"type": "string"}, "expires_at": {"type": "number"},
    }, ["content"]),
    _schema("memory_search", "Search active persistent memories relevant to a query.", {
        "query": {"type": "string"}, "kinds": {"type": "array", "items": {"type": "string"}},
        "limit": {"type": "integer"},
    }, ["query"]),
    _schema("memory_get", "Get one persistent memory by id, or search by legacy keywords.", {
        "id": {"type": "string"}, "keywords": {"type": "string"},
    }, []),
    _schema("memory_forget", "Delete one persistent memory by id.", {
        "id": {"type": "string"},
    }, ["id"]),
    _schema("browser_use", "Automate an Android WebView browser, with up to 3 tabs.", {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "url": {"type": "string"}, "selector": {"type": "string"},
        "text": {"type": "string"}, "script": {"type": "string"},
        "direction": {"type": "string"}, "amount": {"type": "integer"},
        "coordinate_x": {"type": "integer"}, "coordinate_y": {"type": "integer"},
        "tab_id": {"type": "integer"}, "item_selector": {"type": "string"},
        "scroll_count": {"type": "integer"}, "timeout": {"type": "integer"},
        "user_agent": {"type": "string"},
        "viewport_width": {"type": "integer"}, "viewport_height": {"type": "integer"},
        "reset": {"type": "boolean"}, "keywords": {"type": "array", "items": {"type": "string"}},
        "fuzzy": {"type": "boolean"}, "cookies": {"type": "array"},
        "max_depth": {"type": "integer"}, "full_page": {"type": "boolean"},
    }, ["action"]),
    _schema("phone_use", "Control the visible Android screen when the user has enabled phone control. Inspect before using node IDs; include generation with node_id. Screenshot coordinates refer to original_width/original_height.", {
        "action": {"type": "string", "enum": list(PHONE_ACTIONS)},
        "generation": {"type": "integer"}, "node_id": {"type": "integer"},
        "text": {"type": "string"}, "resource_id": {"type": "string"},
        "x": {"type": "integer"}, "y": {"type": "integer"},
        "end_x": {"type": "integer"}, "end_y": {"type": "integer"},
        "duration_ms": {"type": "integer"}, "value": {"type": "string"},
        "direction": {"type": "string", "enum": ["up", "down"]},
        "key": {"type": "string", "enum": ["back", "home", "recents"]},
        "package_name": {"type": "string"}, "present": {"type": "boolean"},
        "timeout_ms": {"type": "integer"},
    }, ["action"]),
]


class ToolExecutor:
    def __init__(self, sandbox: ProotSandbox, browser: BrowserController | None,
                 phone: PhoneController | None = None,
                 on_progress=None, store: Store | None = None):
        self.sandbox = sandbox
        self.browser = browser
        self.phone = phone
        self.on_progress = on_progress
        self.store = store
        self.memory_writer = MemoryWriter(store) if store is not None else None
        self.memory_request = ""
        self.memory_session_id: str | None = None
        self.memory_message_id: int | None = None

    def begin_request(self, request: str, session_id: str | None = None,
                      message_id: int | None = None) -> None:
        self.memory_request = str(request or "")
        self.memory_session_id = session_id
        self.memory_message_id = message_id

    def _browser_progress(self, event: dict[str, Any]) -> None:
        if self.on_progress is not None:
            self.on_progress(event)

    @property
    def schemas(self) -> list[dict]:
        unavailable = set()
        if not getattr(self.sandbox, "available", True):
            unavailable.add("shell_execute")
        if self.browser is None:
            unavailable.add("browser_use")
        if self.phone is None:
            unavailable.add("phone_use")
        return [schema for schema in TOOL_SCHEMAS
                if schema["function"]["name"] not in unavailable]

    def execute(self, name: str, args: dict[str, Any], cancel: threading.Event) -> str:
        try:
            result = self._execute(name, args, cancel)
            return json.dumps(result, ensure_ascii=False)
        except InterruptedError:
            raise
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    def _execute(self, name: str, args: dict[str, Any], cancel: threading.Event) -> Any:
        if name == "shell_execute":
            return self.sandbox.execute(args["command"], args.get("timeout", 900), cancel)
        if name in {"file_read", "file_write", "file_edit"}:
            path = self.sandbox.resolve(args["path"], must_exist=name != "file_write")
            if name == "file_read":
                if path.stat().st_size > 1_000_000:
                    raise SandboxError("文件超过 1 MB")
                return {"content": path.read_text(encoding="utf-8")}
            if name == "file_write":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(args["content"], encoding="utf-8")
                return {"path": args["path"], "bytes": path.stat().st_size}
            old = args["old_text"]
            if not old:
                raise ValueError("old_text 不能为空")
            original = path.read_text(encoding="utf-8")
            if original.count(old) != 1:
                raise ValueError("old_text 必须恰好匹配一次")
            path.write_text(original.replace(old, args["new_text"], 1), encoding="utf-8")
            return {"path": args["path"], "edited": True}
        if name == "memory_write":
            content = str(args.get("content", "")).strip()
            if self.memory_writer is None:
                raise ValueError("长期记忆存储未配置")
            return self.memory_writer.write_from_history(
                request=self.memory_request, content=content,
                kind=args.get("kind", "semantic"), key=args.get("key"),
                source_session_id=self.memory_session_id,
                source_message_id=self.memory_message_id,
                expires_at=args.get("expires_at"),
            )
        if name in {"memory_search", "memory_get"}:
            query = args.get("query", args.get("keywords", ""))
            if self.store is not None:
                if name == "memory_get" and args.get("id"):
                    result = self.store.memory(str(args["id"]))
                    return {"memory": result} if result else {"memory": None}
                return {"matches": self.store.search_memories(
                    str(query), kinds=args.get("kinds"), limit=args.get("limit", 12))}
            return {"matches": []}
        if name == "memory_forget":
            if self.store is None:
                raise ValueError("长期记忆存储未配置")
            return {"deleted": self.store.delete_memory(str(args["id"]))}
        if name == "browser_use":
            if self.browser is None:
                raise RuntimeError("浏览器仅在 Android 中可用")
            self.browser.on_progress = self._browser_progress
            return self.browser.call(args["action"], args, cancel)
        if name == "phone_use":
            if self.phone is None:
                raise RuntimeError("手机操作未启用")
            return self.phone.call(args["action"], args, cancel)
        raise ValueError(f"未知工具：{name}")
