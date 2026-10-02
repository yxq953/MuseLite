"""Agent tool schemas and implementations."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .browser import ACTIONS, BrowserController
from .phone import ACTIONS as PHONE_ACTIONS, PhoneController
from .sandbox import ProotSandbox, SandboxError


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
    _schema("memory_write", "Save a persistent note for future sessions.", {
        "content": {"type": "string"},
    }, ["content"]),
    _schema("memory_get", "Search persistent notes by keywords.", {
        "keywords": {"type": "string"},
    }, []),
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
                 on_progress=None):
        self.sandbox = sandbox
        self.browser = browser
        self.phone = phone
        self.on_progress = on_progress

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
            content = args["content"].strip()
            if not content:
                raise ValueError("记忆内容不能为空")
            self.sandbox.memory.mkdir(parents=True, exist_ok=True)
            path = self.sandbox.memory / (datetime.now().strftime("%Y-%m-%d") + ".md")
            with path.open("a", encoding="utf-8") as output:
                output.write(f"\n## {datetime.now().strftime('%H:%M')}\n{content}\n")
            return {"saved": True, "path": "/var/muselite/memory/" + path.name}
        if name == "memory_get":
            keywords = args.get("keywords", "").casefold().split()
            matches = []
            for path in sorted(self.sandbox.memory.glob("*.md"), reverse=True):
                body = path.read_text(encoding="utf-8")
                if all(word in body.casefold() for word in keywords):
                    matches.append({"file": path.name, "content": body[:8000]})
                if len(matches) >= 10:
                    break
            return {"matches": matches}
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
