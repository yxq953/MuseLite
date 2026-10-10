import json
import threading

import pytest

from muselite_py.agent import Agent
from muselite_py.clipboard import ClipboardController
from muselite_py.desktop import DesktopSandbox
from muselite_py.phone import PhoneController
from muselite_py.storage import Store
from muselite_py.tools import ToolExecutor


class Bridge:
    def __init__(self):
        self.calls = []
        self.text = "中文 😀"
        self.foreground = True
        self.chat_available = True

    def clipboard_call(self, action, params):
        self.calls.append(("clipboard", action, params))
        if action == "read":
            if not self.foreground:
                raise RuntimeError("Android 限制后台读取剪贴板，请回到 MuseLite 前台后重试")
            end = params["max_chars"]
            return {"empty": not self.text, "content": self.text[:end], "truncated": len(self.text) > end}
        self.text = params["text"]
        return {"written": True, "chars": len(self.text)}

    def phone_call(self, action, params):
        self.calls.append(("phone", action, params))
        assert action == "read_chat"  # No taps, typing, paste or send in this workflow.
        if not self.chat_available:
            raise RuntimeError("读取聊天界面超时：请切换到聊天界面")
        return {"package": "test.chat", "visible_only": True, "truncated": False,
                "nodes": [{"text": "明天下午三点见？", "bounds": {"top": 120}, "editable": False}]}


def make_tools(tmp_path, bridge):
    return ToolExecutor(DesktopSandbox(tmp_path), None, PhoneController(bridge),
                        clipboard=ClipboardController(bridge))


def test_clipboard_unicode_empty_limits_and_background_error(tmp_path):
    bridge = Bridge()
    tools = make_tools(tmp_path, bridge)
    cancel = threading.Event()
    assert json.loads(tools.execute("clipboard_read", {"max_chars": 4}, cancel))["content"] == "中文 😀"
    page = json.loads(tools.execute("clipboard_read", {"max_chars": 2}, cancel))
    assert page["content"] == "中文" and page["truncated"]
    bridge.foreground = False
    result = json.loads(tools.execute("clipboard_read", {}, cancel))
    assert "前台" in result["error"] and "empty" not in result
    text = "😀" * 50000
    result = json.loads(tools.execute("clipboard_write", {"text": text}, cancel))
    assert result == {"written": True, "chars": 50000} and bridge.text == text
    tools.execute("clipboard_write", {"text": ""}, cancel)
    bridge.foreground = True
    assert json.loads(tools.execute("clipboard_read", {}, cancel))["empty"]


@pytest.mark.parametrize("name,args", [
    ("clipboard_write", {}), ("clipboard_write", {"text": None}),
    ("clipboard_write", {"text": 123}), ("clipboard_write", {"text": "x" * 50001}),
    ("clipboard_read", {"max_chars": 0}), ("clipboard_read", {"max_chars": 50001}),
    ("clipboard_read", {"max_chars": True}), ("clipboard_read", {"max_chars": "20"}),
    ("chat_read", {"timeout_ms": -1}), ("chat_read", {"timeout_ms": 30001}),
    ("chat_read", {"timeout_ms": True}), ("chat_read", {"package_name": 123}),
])
def test_invalid_arguments_never_reach_android(tmp_path, name, args):
    bridge = Bridge()
    result = json.loads(make_tools(tmp_path, bridge).execute(name, args, threading.Event()))
    assert "error" in result and bridge.calls == []


def test_availability_and_stop_do_not_touch_clipboard_or_screen(tmp_path):
    bridge = Bridge()
    sandbox = DesktopSandbox(tmp_path)
    desktop = ToolExecutor(sandbox, None)
    names = {schema["function"]["name"] for schema in desktop.schemas}
    assert not {"clipboard_read", "clipboard_write", "chat_read"} & names
    clipboard_only = ToolExecutor(sandbox, None, clipboard=ClipboardController(bridge))
    names = {schema["function"]["name"] for schema in clipboard_only.schemas}
    assert {"clipboard_read", "clipboard_write"} <= names and "chat_read" not in names
    assert "error" in json.loads(clipboard_only.execute("chat_read", {}, threading.Event()))
    cancel = threading.Event()
    cancel.set()
    for name, args in (("clipboard_read", {}), ("clipboard_write", {"text": "reply"}), ("chat_read", {})):
        with pytest.raises(InterruptedError):
            make_tools(tmp_path, bridge).execute(name, args, cancel)
    assert bridge.calls == []


def test_chat_timeout_is_an_error_not_fake_context(tmp_path):
    bridge = Bridge()
    bridge.chat_available = False
    result = json.loads(make_tools(tmp_path, bridge).execute("chat_read", {
        "timeout_ms": 200, "package_name": "test.chat"}, threading.Event()))
    assert "超时" in result["error"] and "nodes" not in result
    assert bridge.calls == [("phone", "read_chat", {"timeout_ms": 200, "package_name": "test.chat"})]


def test_agent_reads_chat_and_copies_recommended_reply_without_sending(tmp_path):
    bridge = Bridge()
    bridge.foreground = False
    tools = make_tools(tmp_path / "data", bridge)
    store = Store(tmp_path / "app.db")
    sid = store.create_session()

    class Client:
        def __init__(self):
            self.count = 0

        def complete(self, messages, schemas, on_text, cancel):
            self.count += 1
            if self.count == 1:
                name, args = "chat_read", {"package_name": "test.chat"}
            elif self.count == 2:
                context = json.loads(messages[-1]["content"])
                assert context["nodes"][0]["text"] == "明天下午三点见？"
                name, args = "clipboard_write", {"text": "好的，明天下午三点见！😀"}
            else:
                result = json.loads(messages[-1]["content"])
                assert result["written"]
                return {"role": "assistant", "content": "回复已复制到剪贴板，可自行粘贴。", "tool_calls": []}
            return {"role": "assistant", "content": "", "tool_calls": [{
                "id": f"reply_{self.count}", "type": "function", "function": {
                    "name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}

    Agent(store, Client(), tools).run(sid, "读取聊天界面，推荐一个回复并复制到剪贴板")
    assert bridge.text == "好的，明天下午三点见！😀"
    assert [(kind, action) for kind, action, _ in bridge.calls] == [("phone", "read_chat"), ("clipboard", "write")]
    assert [m["role"] for m in store.messages(sid)] == ["user", "assistant", "tool", "assistant", "tool", "assistant"]
    store.close()
