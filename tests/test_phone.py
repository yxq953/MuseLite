import json
import threading

import pytest

from muselite_py.agent import Agent
from muselite_py.desktop import DesktopSandbox
from muselite_py.phone import PhoneController
from muselite_py.storage import Store
from muselite_py.tools import ToolExecutor


class FakePhoneBridge:
    def __init__(self, path=None):
        self.path = path
        self.calls = []

    def phone_call(self, action, params):
        self.calls.append((action, params))
        if action == "screenshot":
            return {"path": str(self.path), "mime": "image/jpeg", "width": 10, "height": 10}
        return {"performed": True}


def test_phone_tool_is_explicitly_available_and_cancelled(tmp_path):
    bridge = FakePhoneBridge()
    controller = PhoneController(bridge)
    tools = ToolExecutor(DesktopSandbox(tmp_path), None, controller)
    assert "phone_use" in {item["function"]["name"] for item in tools.schemas}
    assert json.loads(tools.execute("phone_use", {"action": "tap", "x": 1, "y": 2},
                                    threading.Event())) == {"performed": True}
    assert bridge.calls == [("tap", {"action": "tap", "x": 1, "y": 2})]
    with pytest.raises(ValueError, match="wait 需要"):
        controller.call("wait", {})
    cancel = threading.Event(); cancel.set()
    with pytest.raises(InterruptedError):
        controller.call("inspect", {}, cancel)
    assert len(bridge.calls) == 1


@pytest.mark.parametrize("supports_images", [True, False])
def test_phone_screenshot_is_transient_in_agent_context(tmp_path, supports_images):
    image = tmp_path / "phone.jpg"
    image.write_bytes(b"fake-jpeg-bytes")
    bridge = FakePhoneBridge(image)
    store = Store(tmp_path / "app.sqlite3")
    sid = store.create_session()

    class Client:
        config = type("Config", (), {"supports_images": supports_images})()

        def __init__(self):
            self.calls = 0
            self.seen = None

        def complete(self, messages, schemas, on_text, cancel):
            self.calls += 1
            if self.calls == 1:
                return {"role": "assistant", "content": "", "tool_calls": [{
                    "id": "phone_1", "type": "function", "function": {
                        "name": "phone_use", "arguments": '{"action":"screenshot"}'}}]}
            self.seen = messages[-1]
            return {"role": "assistant", "content": "完成", "tool_calls": []}

    client = Client()
    tools = ToolExecutor(DesktopSandbox(tmp_path / "data"), None, PhoneController(bridge))
    Agent(store, client, tools).run(sid, "查看屏幕")
    saved = store.messages(sid)[-2]
    assert saved["role"] == "tool" and isinstance(saved["content"], str)
    assert "base64" not in saved["content"] and "path" not in saved["content"]
    assert not image.exists()
    if supports_images:
        assert client.seen["content"][1]["type"] == "image_url"
    else:
        assert "未启用图像输入" in client.seen["content"]
