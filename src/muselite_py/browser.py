"""Browser automation API backed by the Android WebView bridge."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Protocol


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
    def __init__(self, bridge: BrowserBridge,
                 on_progress: Callable[[dict[str, Any]], None] | None = None,
                 on_show: Callable[[], None] | None = None,
                 on_preview: Callable[[dict[str, Any]], None] | None = None):
        self.bridge = bridge
        self.on_progress = on_progress
        self.on_show = on_show
        self.on_preview = on_preview

    def _emit_progress(self, action: str, result: Any,
                       phase: str = "result") -> None:
        event = {"action": action, "phase": phase, "result": result}
        if self.on_progress is not None:
            try:
                self.on_progress(event)
            except Exception:
                # Progress is best effort and must never break the browser operation.
                pass
        if phase != "start" and self.on_preview is not None:
            try:
                # The compact preview is independent from the chat progress
                # callback.  It must still update when a browser call is made
                # outside an active Agent stream.
                self.on_preview(event)
            except Exception:
                pass

    def call(self, action: str, params: dict[str, Any],
             cancel: threading.Event | None = None) -> dict[str, Any]:
        if cancel is not None and cancel.is_set():
            raise InterruptedError("浏览器操作已取消")
        if action not in ACTIONS:
            raise ValueError(f"不支持的浏览器操作：{action}")
        # Keep the live page available for the user while the Agent works. The
        # Android implementation renders this as a touch-friendly bottom panel.
        if action != "show_browser" and self.on_show is not None:
            try:
                self.on_show()
            except Exception:
                pass
        self._emit_progress(action, None, "start")
        if action == "scroll_and_collect":
            result = self._scroll_and_collect(params, cancel)
            self._emit_progress(action, result)
            return result
        if action == "wait_for_dom_stable":
            result = self._wait_for_dom_stable(params, cancel)
            self._emit_progress(action, result)
            return result
        result = self.bridge.call(action, params)
        if cancel is not None and cancel.is_set():
            raise InterruptedError("浏览器操作已取消")
        self._emit_progress(action, result)
        return result

    def _scroll_and_collect(self, params: dict[str, Any],
                            cancel: threading.Event | None) -> dict[str, Any]:
        selector = params.get("item_selector")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("scroll_and_collect 需要 item_selector")
        count = min(max(int(params.get("scroll_count", 5)), 1), 50)
        seen: dict[str, dict[str, str]] = {}
        for _scroll_index in range(count):
            if cancel is not None and cancel.is_set():
                raise InterruptedError("浏览器操作已取消")
            script = """return Array.from(document.querySelectorAll(%s)).map((e) =>
                ({text:(e.innerText||'').trim(),html:e.outerHTML.slice(0,3000)}))""" % json.dumps(selector)
            result = self.bridge.call("execute_js", {**params, "script": script})
            self._emit_progress("scroll_and_collect", {
                "phase": "collect", "items": result.get("result") or [],
                "scroll": _scroll_index,
            })
            for item in result.get("result") or []:
                if not isinstance(item, dict):
                    continue
                key = item.get("text") or item.get("html")
                if key:
                    seen[key] = item
            scroll_result = self.bridge.call(
                "scroll", {**params, "direction": "down",
                            "amount": params.get("amount", 500)})
            self._emit_progress("scroll_and_collect", {
                "phase": "scroll", "scroll": _scroll_index,
                "result": scroll_result,
            })
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
