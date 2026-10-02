"""OpenAI-compatible Chat Completions client with SSE tool-call assembly."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    model: str
    api_key: str
    supports_images: bool = False

    @property
    def endpoint(self) -> str:
        base = self.base_url.strip().rstrip("/")
        if not base.startswith("https://") and not base.startswith("http://127.0.0.1:"):
            raise ValueError("模型地址须使用 HTTPS")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"


def _error_message(exc: urllib.error.HTTPError) -> str:
    body = exc.read(2048).decode("utf-8", "replace")
    try:
        body = json.loads(body).get("error", {}).get("message", body)
    except (ValueError, AttributeError):
        pass
    return f"HTTP {exc.code}: {body}"


class OpenAICompatibleClient:
    def __init__(self, config: ProviderConfig, opener: Any = None):
        self.config = config
        self.opener = opener or urllib.request
        self._active_response: Any = None
        self._response_lock = threading.Lock()

    def stop(self) -> None:
        with self._response_lock:
            response = self._active_response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_text: Callable[[str], None],
        cancel: threading.Event,
    ) -> dict[str, Any]:
        if not self.config.model.strip():
            raise ProviderError("请先配置模型 ID")
        if not self.config.api_key.strip():
            raise ProviderError("请先配置 API Key")
        body: dict[str, Any] = {
            "model": self.config.model.strip(), "messages": messages, "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        request = urllib.request.Request(
            self.config.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream",
                     "Authorization": "Bearer " + self.config.api_key.strip()},
            method="POST",
        )
        chunks: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        finish_reason = None
        try:
            with self.opener.urlopen(request, timeout=60) as response:
                with self._response_lock:
                    self._active_response = response
                try:
                    for raw in response:
                        if cancel.is_set():
                            raise InterruptedError("已停止生成")
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        if not payload:
                            continue
                        try:
                            event = json.loads(payload)
                        except ValueError as exc:
                            raise ProviderError("模型返回了无效 SSE JSON") from exc
                        if event.get("error"):
                            raise ProviderError(str(event["error"]))
                        for choice in event.get("choices", []):
                            finish_reason = choice.get("finish_reason") or finish_reason
                            delta = choice.get("delta") or {}
                            piece = delta.get("content")
                            if isinstance(piece, str) and piece:
                                chunks.append(piece)
                                on_text(piece)
                            for fragment in delta.get("tool_calls") or []:
                                index = fragment.get("index", 0)
                                target = calls.setdefault(index, {
                                    "id": "", "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                })
                                if fragment.get("id"):
                                    target["id"] = fragment["id"]
                                function = fragment.get("function") or {}
                                target["function"]["name"] += function.get("name") or ""
                                target["function"]["arguments"] += function.get("arguments") or ""
                finally:
                    with self._response_lock:
                        self._active_response = None
        except urllib.error.HTTPError as exc:
            raise ProviderError(_error_message(exc)) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if cancel.is_set():
                raise InterruptedError("已停止生成") from exc
            raise ProviderError(f"网络请求失败：{exc}") from exc
        except Exception as exc:
            if cancel.is_set():
                raise InterruptedError("已停止生成") from exc
            raise
        if cancel.is_set():
            raise InterruptedError("已停止生成")
        ordered = [calls[i] for i in sorted(calls)]
        if not chunks and not ordered and finish_reason is None:
            raise ProviderError("模型返回了空响应")
        return {"role": "assistant", "content": "".join(chunks), "tool_calls": ordered}
