import base64
import json
import threading
from types import SimpleNamespace

import pytest

from muselite_py.agent import Agent
from muselite_py.chat_reply import ChatReplyController
from muselite_py.desktop import DesktopSandbox
from muselite_py.storage import Store
from muselite_py.tools import ToolExecutor


class Bridge:
    def __init__(self, tmp_path):
        self.path = tmp_path / "private-screen.jpg"
        self.calls = []
        self.token = None
        self.written = None
        self.number = 0

    def reply_hint_call(self, action, args):
        self.calls.append((action, args.copy()))
        if action == "enable":
            self.number += 1
            self.token = str(self.number)
            return {"token": self.token}
        if action == "disable":
            if not args.get("token") or args["token"] == self.token:
                self.token = None
            return {"enabled": self.token is not None}
        if action == "capture":
            assert args["token"] == self.token
            self.path.write_bytes(b"fake screenshot bytes")
            return {"path": str(self.path), "package": "example.chat"}
        if action == "finish":
            if args["token"] != self.token:
                raise RuntimeError("request invalidated")
            self.written = args["text"]
            return {"written": True}
        return {}


class Client:
    config = SimpleNamespace(supports_images=True, api_key="fake test key")

    def __init__(self, content='{"reply":"好的，明天见！"}'):
        self.content = content
        self.calls = []
        self.hook = None
        self.stopped = False

    def stop(self):
        self.stopped = True

    def complete(self, messages, tools, on_text, cancel):
        self.calls.append((messages, tools))
        if self.hook:
            self.hook()
        return {"role": "assistant", "content": self.content, "tool_calls": []}


def setup(tmp_path, client=None):
    store = Store(tmp_path / "test.db")
    sid = store.create_session()
    bridge = Bridge(tmp_path)
    client = client or Client()
    controller = ChatReplyController(bridge, store, lambda: client)
    controller.set_session(sid)
    controller.configure({"action": "enable", "style": "礼貌、简洁"}, sid, threading.Event())
    return controller, bridge, client, store, sid


def request(controller, sid):
    return {"token": controller.token, "session_id": sid, "request_id": "click-1"}


def test_enable_waits_for_click_then_sends_image_and_copies_only_reply(tmp_path):
    controller, bridge, client, store, sid = setup(tmp_path)
    assert not client.calls
    assert not bridge.path.exists()
    assert not any(a == "capture" for a, _ in bridge.calls)
    store.set_setting("agent_soul", "温和，不用表情")
    store.add_message(sid, {"role": "user", "content": "别太正式"})
    result = controller.run(request(controller, sid))
    assert result["written"] and bridge.written == "好的，明天见！"
    messages, tools = client.calls[0]
    assert tools == []
    assert "礼貌、简洁" in messages[0]["content"] and "不用表情" in messages[0]["content"]
    assert "别太正式" in messages[1]["content"][0]["text"]
    encoded = messages[1]["content"][1]["image_url"]["url"].split(",", 1)[1]
    assert base64.b64decode(encoded) == b"fake screenshot bytes"
    assert not bridge.path.exists()
    assert store.messages(sid)[-1]["content"] == "好的，明天见！"


@pytest.mark.parametrize("content", [
    '{"error":"请打开聊天窗口"}', "", "not JSON", "[]", '{"reply":""}',
    json.dumps({"reply": "x" * 10001}),
])
def test_failed_or_unreadable_draft_does_not_change_clipboard(tmp_path, content):
    controller, bridge, client, store, sid = setup(tmp_path, Client(content))
    with pytest.raises(RuntimeError):
        controller.run(request(controller, sid))
    assert bridge.written is None
    assert not bridge.path.exists()
    assert not store.messages(sid)
    assert bridge.calls[-1][0] == "error"


def test_close_during_generation_invalidates_old_copy(tmp_path):
    controller, bridge, client, store, sid = setup(tmp_path)
    client.hook = lambda: controller.set_session(None)
    with pytest.raises(InterruptedError):
        controller.run(request(controller, sid))
    assert client.stopped and bridge.token is None
    assert bridge.written is None and not store.messages(sid)


def test_switch_conversation_and_stale_button_request(tmp_path):
    controller, bridge, client, store, sid = setup(tmp_path)
    old = request(controller, sid)
    controller.set_session(store.create_session())
    with pytest.raises(InterruptedError):
        controller.run(old)
    with pytest.raises(RuntimeError, match="结束"):
        controller.configure({"action": "enable"}, sid, threading.Event())
    assert not client.calls and bridge.token is None


def test_old_close_cannot_remove_reenabled_overlay(tmp_path):
    controller, bridge, client, store, sid = setup(tmp_path)
    old = controller.token
    controller.configure({"action": "enable", "style": "幽默"}, sid, threading.Event())
    controller.disable(old)
    assert bridge.token == controller.token and controller.token != old


def test_missing_vision_support_does_not_enable(tmp_path):
    client = Client()
    client.config = SimpleNamespace(supports_images=False, api_key="fake")
    store = Store(tmp_path / "test.db")
    sid = store.create_session()
    bridge = Bridge(tmp_path)
    controller = ChatReplyController(bridge, store, lambda: client)
    controller.set_session(sid)
    with pytest.raises(RuntimeError, match="识图"):
        controller.configure({"action": "enable"}, sid, threading.Event())
    assert bridge.token is None


def test_screenshot_failure_and_cleanup(tmp_path):
    controller, bridge, client, store, sid = setup(tmp_path)
    original = bridge.reply_hint_call
    def fail(action, args):
        if action == "capture":
            raise RuntimeError("页面禁止截图")
        return original(action, args)
    bridge.reply_hint_call = fail
    with pytest.raises(RuntimeError, match="禁止截图"):
        controller.run(request(controller, sid))
    assert not client.calls and bridge.written is None
    assert not controller._running


def test_close_during_capture_deletes_image_without_model_call(tmp_path):
    controller, bridge, client, store, sid = setup(tmp_path)
    original = bridge.reply_hint_call
    def capture_and_close(action, args):
        result = original(action, args)
        if action == "capture":
            controller.set_session(None)
        return result
    bridge.reply_hint_call = capture_and_close
    with pytest.raises(InterruptedError):
        controller.run(request(controller, sid))
    assert not client.calls and bridge.written is None and not bridge.path.exists()


def test_duplicate_click_rejected_without_second_capture(tmp_path):
    controller, bridge, client, store, sid = setup(tmp_path)
    current = request(controller, sid)
    def click_again():
        with pytest.raises(RuntimeError, match="稍候"):
            controller.run(current)
    client.hook = click_again
    controller.run(current)
    assert sum(action == "capture" for action, _ in bridge.calls) == 1


def test_agent_can_enable_overlay_without_capturing(tmp_path):
    controller, bridge, client, store, sid = setup(tmp_path)
    controller.disable()
    class ToolClient:
        count = 0
        def complete(self, messages, tools, on_text, cancel):
            self.count += 1
            calls = ([{"id": "hint1", "type": "function", "function": {
                "name": "chat_hint", "arguments": '{"action":"enable","style":"简洁"}'}}]
                     if self.count == 1 else [])
            return {"role": "assistant", "content": "" if calls else "已开启", "tool_calls": calls}
    sandbox = DesktopSandbox(tmp_path / "sandbox")
    sandbox.available = True
    executor = ToolExecutor(sandbox, None, store=store, chat_reply=controller)
    Agent(store, ToolClient(), executor).run(sid, "我需要这个聊天提示的功能")
    assert bridge.token is not None and controller.style == "简洁"
    assert not any(action == "capture" for action, _ in bridge.calls)


def test_unavailable_tool_not_exposed(tmp_path):
    executor = ToolExecutor(DesktopSandbox(tmp_path), None)
    assert "chat_hint" not in {item["function"]["name"] for item in executor.schemas}
