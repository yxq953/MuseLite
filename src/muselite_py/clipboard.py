"""Explicit, bounded text clipboard tools backed by Android."""

from __future__ import annotations

import threading


class ClipboardController:
    def __init__(self, bridge):
        self.bridge = bridge

    def call(self, action: str, args: dict, cancel: threading.Event) -> dict:
        if cancel.is_set():
            raise InterruptedError("已停止剪贴板操作")
        if action == "read":
            limit = args.get("max_chars", 12000)
            if type(limit) is not int or not 1 <= limit <= 50000:
                raise ValueError("max_chars 必须在 1 到 50000 之间")
            params = {"max_chars": limit}
        elif action == "write":
            text = args.get("text")
            if not isinstance(text, str):
                raise ValueError("text 必须是文本")
            if len(text) > 50000:
                raise ValueError("剪贴板文本不能超过 50000 字符")
            params = {"text": text}
        else:
            raise ValueError("未知剪贴板操作")
        return self.bridge.clipboard_call(action, params)
