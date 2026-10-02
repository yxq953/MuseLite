"""Browser automation API backed by the Android WebView bridge."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Protocol


ACTIONS = (
    "navigate", "screenshot", "click", "type", "get_text", "scroll",
    "get_page_info", "execute_js", "find_elements", "hover", "get_readable",
    "set_user_agent", "set_viewport", "get_backbone", "fetch", "new_tab",
    "close_tab", "list_tabs", "get_cookies", "set_cookies",
    "scroll_and_collect", "wait_for_dom_stable",
)


class BrowserBridge(Protocol):
    def call(self, action: str, params: dict[str, Any]) -> dict[str, Any]: ...


class BrowserController:
    def __init__(self, bridge: BrowserBridge):
        self.bridge = bridge

    def call(self, action: str, params: dict[str, Any],
             cancel: threading.Event | None = None) -> dict[str, Any]:
        if cancel is not None and cancel.is_set():
            raise InterruptedError("浏览器操作已取消")
        if action not in ACTIONS:
            raise ValueError(f"不支持的浏览器操作：{action}")
        if action == "scroll_and_collect":
            return self._scroll_and_collect(params, cancel)
        if action == "wait_for_dom_stable":
            return self._wait_for_dom_stable(params, cancel)
        result = self.bridge.call(action, params)
        if cancel is not None and cancel.is_set():
            raise InterruptedError("浏览器操作已取消")
        return result

    def _scroll_and_collect(self, params: dict[str, Any],
                            cancel: threading.Event | None) -> dict[str, Any]:
        selector = params.get("item_selector")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("scroll_and_collect 需要 item_selector")
        count = min(max(int(params.get("scroll_count", 5)), 1), 50)
        seen: dict[str, dict[str, str]] = {}
        for _ in range(count):
            if cancel is not None and cancel.is_set():
                raise InterruptedError("浏览器操作已取消")
            script = """return Array.from(document.querySelectorAll(%s)).map((e) =>
                ({text:(e.innerText||'').trim(),html:e.outerHTML.slice(0,3000)}))""" % json.dumps(selector)
            result = self.bridge.call("execute_js", {**params, "script": script})
            for item in result.get("result") or []:
                if not isinstance(item, dict):
                    continue
                key = item.get("text") or item.get("html")
                if key:
                    seen[key] = item
            self.bridge.call("scroll", {**params, "direction": "down",
                                        "amount": params.get("amount", 500)})
            if cancel is not None:
                if cancel.wait(0.4):
                    raise InterruptedError("浏览器操作已取消")
            else:
                time.sleep(0.4)
        keywords = params.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        selected = [item for item in seen.values() if not keywords or any(
            str(word).casefold() in item.get("text", "").casefold() for word in keywords)]
        return {"items": selected, "count": len(selected), "total": len(seen)}

    def _wait_for_dom_stable(self, params: dict[str, Any],
                             cancel: threading.Event | None) -> dict[str, Any]:
        timeout = min(max(float(params.get("timeout", 10_000)) / 1000, 0.2), 60)
        until = time.monotonic() + timeout
        last = None
        stable = 0
        while time.monotonic() < until:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("浏览器操作已取消")
            result = self.bridge.call("execute_js", {
                **params, "script": "const s=document.body?.innerHTML||'';let h=2166136261;"
                "for(let i=0;i<s.length;i++)h=Math.imul(h^s.charCodeAt(i),16777619);"
                "return {size:s.length,hash:h}"
            })
            sample = result.get("result")
            stable = stable + 1 if sample == last else 0
            if stable >= 1 and isinstance(sample, dict) and sample.get("size", 0) > 0:
                return {"stable": True, "dom_size": sample["size"]}
            last = sample
            if cancel is not None:
                if cancel.wait(0.2):
                    raise InterruptedError("浏览器操作已取消")
            else:
                time.sleep(0.2)
        return {"stable": False, "dom_size": last.get("size") if isinstance(last, dict) else 0}
