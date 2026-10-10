"""Read and export Agent documents in the user-selected Android document tree."""

from __future__ import annotations

import threading
from pathlib import PurePosixPath


MAX_DOCUMENT_BYTES = 25 * 1024 * 1024


def document_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("文档路径不能为空")
    parts = value.split("/")
    if (value.startswith("/") or any(not part.strip() or part in {".", ".."} for part in parts)
            or any(char in value for char in '\\:*?"<>|')
            or any(ord(char) < 32 for char in value)):
        raise ValueError("请使用保存目录内的相对路径，例如 报告/总结.md；不能包含 .. 或绝对路径")
    return str(PurePosixPath(value))


class DocumentController:
    def __init__(self, bridge, sandbox):
        self.bridge, self.sandbox = bridge, sandbox

    def directory(self) -> dict:
        return self.bridge.documents_call("status", {})

    def browse(self, action: str, args: dict, cancel: threading.Event) -> dict:
        if cancel.is_set():
            raise InterruptedError("已停止读取文档")
        if action not in {"list", "read"}:
            raise ValueError("未知文档读取操作")
        path = args.get("path", "")
        if action == "list" and path == "":
            path = ""
        else:
            path = document_path(path)
        params = {"path": path}
        options = (("offset", 0, 0, 2147483647), ("limit", 100, 1, 200)) if action == "list" else (
            ("offset", 0, 0, 2147483647), ("max_chars", 12000, 1, 50000))
        for name, default, minimum, maximum in options:
            value = args.get(name, default)
            if (type(value) is not int or value < minimum
                    or (maximum is not None and value > maximum)):
                raise ValueError(f"{name} 超出允许范围")
            params[name] = value
        return self.bridge.documents_call(action, params)

    def save(self, args: dict, cancel: threading.Event) -> dict:
        if cancel.is_set():
            raise InterruptedError("已停止保存文档")
        path = document_path(args.get("path", ""))
        if ("content" in args) == ("source_path" in args):
            raise ValueError("content 和 source_path 必须提供其中一个")
        params = {"path": path}
        if "content" in args:
            content = args["content"]
            if not isinstance(content, str):
                raise ValueError("content 必须是文本")
            if len(content.encode("utf-8")) > MAX_DOCUMENT_BYTES:
                raise ValueError("文档超过 25 MB")
            params["content"] = content
        else:
            source = self.sandbox.resolve(args["source_path"], must_exist=True)
            if not source.is_file():
                raise ValueError("source_path 必须是工作区内的文件")
            if source.stat().st_size > MAX_DOCUMENT_BYTES:
                raise ValueError("文档超过 25 MB")
            params["source_file"] = str(source)
        if cancel.is_set():
            raise InterruptedError("已停止保存文档")
        return self.bridge.documents_call("save", params)
