"""Focused phone interaction API backed by the Android accessibility bridge."""

from __future__ import annotations

import threading
from typing import Any


ACTIONS = (
    "status", "inspect", "screenshot", "tap", "long_press", "type", "clear",
    "swipe", "scroll", "press", "open_app", "wait", "read_chat",
)


class PhoneController:
    def __init__(self, bridge):
        self.bridge = bridge

    def call(self, action: str, params: dict[str, Any],
             cancel: threading.Event | None = None) -> dict[str, Any]:
        if action not in ACTIONS:
            raise ValueError(f"不支持的手机操作：{action}")
        if cancel is not None and cancel.is_set():
            raise InterruptedError("手机操作已取消")
        if action == "read_chat":
            timeout = params.get("timeout_ms", 30000)
            if type(timeout) is not int or not 200 <= timeout <= 30000:
                raise ValueError("timeout_ms 必须在 200 到 30000 之间")
            package = params.get("package_name", "")
            if not isinstance(package, str):
                raise ValueError("package_name 必须是文本")
            params = {"timeout_ms": timeout, "package_name": package}
        if action in {"tap", "long_press"}:
            coordinate = "x" in params or "y" in params
            selectors = sum(key in params for key in ("node_id", "text", "resource_id"))
            if int(coordinate) + selectors != 1:
                raise ValueError("点击需要坐标 x/y 或一个节点选择器")
            if coordinate and not ("x" in params and "y" in params):
                raise ValueError("坐标点击需要 x 和 y")
        if "node_id" in params and "generation" not in params:
            raise ValueError("node_id 需要 inspect 返回的 generation")
        if action in {"type", "clear"} and action == "type" and not isinstance(params.get("value"), str):
            raise ValueError("type 需要 value 文本")
        if action == "wait" and not any(key in params for key in ("text", "resource_id")):
            raise ValueError("wait 需要 text 或 resource_id")
        result = self.bridge.phone_call(action, params)
        if cancel is not None and cancel.is_set():
            raise InterruptedError("手机操作已取消")
        return result
