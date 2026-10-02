import io
import json
import tarfile
import threading
from pathlib import Path

import pytest

from muselite_py.agent import Agent
from muselite_py.browser import BrowserController
from muselite_py.desktop import DesktopBridge, DesktopSandbox
from muselite_py.provider import OpenAICompatibleClient, ProviderConfig, ProviderError
from muselite_py.sandbox import ProotSandbox, SandboxError, install_rootfs
from muselite_py.storage import Store
from muselite_py.tools import ToolExecutor


class FakeResponse:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def __iter__(self):
        return iter(self.lines)


class FakeOpener:
    def __init__(self, lines):
        self.lines = lines
        self.request = None

    def urlopen(self, request, timeout):
        self.request = request
        return FakeResponse(self.lines)


def test_stream_assembles_split_tool_call_and_custom_url():
    events = [
        {"choices": [{"delta": {"content": "查"}}]},
        {"choices": [{"delta": {"content": "询", "tool_calls": [
            {"index": 0, "id": "call_1", "function": {"name": "shell_execute", "arguments": '{"com'}}
        ]}}]},
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": 'mand":"pwd"}'}}
        ]}, "finish_reason": "tool_calls"}]},
    ]
    opener = FakeOpener([f"data: {json.dumps(item)}\n".encode() for item in events] +
                        [b"data: [DONE]\n"])
    client = OpenAICompatibleClient(
        ProviderConfig("https://api.deepseek.com/v1/", "deepseek-chat", "secret"), opener)
    chunks = []
    reply = client.complete([{"role": "user", "content": "hi"}], [], chunks.append,
                            threading.Event())
    assert opener.request.full_url == "https://api.deepseek.com/v1/chat/completions"
    assert opener.request.get_header("Authorization") == "Bearer secret"
    assert chunks == ["查", "询"]
    assert reply["tool_calls"][0]["function"]["arguments"] == '{"command":"pwd"}'


def test_stream_rejects_silent_empty_completion():
    client = OpenAICompatibleClient(
        ProviderConfig("https://example.com/v1", "test", "key"), FakeOpener([]))
    with pytest.raises(ProviderError, match="空响应"):
        client.complete([], [], lambda _s: None, threading.Event())


def test_session_and_tool_roundtrip(tmp_path):
    store = Store(tmp_path / "app.sqlite3")
    sid = store.create_session()
    store.add_message(sid, {"role": "user", "content": "你好"})
    store.add_message(sid, {"role": "assistant", "content": "", "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "file_read", "arguments": "{}"}}
    ]})
    store.add_message(sid, {"role": "tool", "tool_call_id": "call_1", "content": "done"})
    store.close()
    store = Store(tmp_path / "app.sqlite3")
    messages = store.messages(sid)
    assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
    assert messages[-1]["tool_call_id"] == "call_1"
    store.delete_session(sid)
    assert store.messages(sid) == []
    store.close()


def test_sandbox_rejects_path_escape_and_archive_escape(tmp_path):
    sandbox = ProotSandbox(tmp_path / "data", tmp_path / "assets", tmp_path / "lib")
    with pytest.raises(SandboxError):
        sandbox.resolve("relative/path")
    with pytest.raises(SandboxError):
        sandbox.resolve("/var/muselite/workspace/../../outside")
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        data = b"bad"
        item = tarfile.TarInfo("../outside")
        item.size = len(data)
        output.addfile(item, io.BytesIO(data))
    with pytest.raises(SandboxError):
        install_rootfs(archive, tmp_path / "root")
    assert not (tmp_path / "outside").exists()


def test_bundled_alpine_extracts_with_guest_absolute_links(tmp_path, monkeypatch):
    archive = Path(__file__).parents[1] / "vendor/assets/alpine-minirootfs.tar"
    links = []
    monkeypatch.setattr(Path, "symlink_to", lambda path, target: links.append((path, target)))
    root = tmp_path / "alpine"
    install_rootfs(archive, root)
    assert (root / ".muselite-rootfs-ready").is_file()
    assert (root / "bin/busybox").is_file()
    assert (root / "usr/lib/os-release").is_file()
    assert any(path.name == "sh" and path.parent.name == "bin" and target == "/bin/busybox"
               for path, target in links)


def test_alpine_rejects_writes_through_archive_links(tmp_path):
    archive = tmp_path / "bad-link.tar"
    with tarfile.open(archive, "w") as output:
        link = tarfile.TarInfo("escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        output.addfile(link)
    with pytest.raises(SandboxError, match="越界链接"):
        install_rootfs(archive, tmp_path / "root")

    with tarfile.open(archive, "w") as output:
        link = tarfile.TarInfo("alias")
        link.type = tarfile.SYMTYPE
        link.linkname = "/bin"
        output.addfile(link)
        data = b"bad"
        item = tarfile.TarInfo("alias/file")
        item.size = len(data)
        output.addfile(item, io.BytesIO(data))
    with pytest.raises(SandboxError, match="穿过符号链接"):
        install_rootfs(archive, tmp_path / "root")


def test_shell_uses_alpine_path_and_home(tmp_path, monkeypatch):
    sandbox = ProotSandbox(tmp_path / "data", tmp_path / "assets", tmp_path / "lib")
    sandbox.app_dir.mkdir()
    monkeypatch.setattr(sandbox, "prepare", lambda: None)
    captured = {}

    def run_once(args, env, *_rest):
        captured.update(args=args, env=env)
        return {"output": "hello\n", "exit_code": 0, "duration_ms": 1}

    monkeypatch.setattr(sandbox, "_run_once", run_once)
    assert sandbox.execute("echo hello")["exit_code"] == 0
    assert captured["env"]["PATH"].endswith(":/bin")
    assert captured["env"]["HOME"] == "/root"
    assert captured["args"][-3:] == ["/bin/sh", "-c", "echo hello"]


def test_file_and_memory_tools(tmp_path):
    sandbox = ProotSandbox(tmp_path / "data", tmp_path / "assets", tmp_path / "lib")
    tools = ToolExecutor(sandbox, None)
    cancel = threading.Event()
    path = "/var/muselite/workspace/note.txt"
    assert json.loads(tools.execute("file_write", {"path": path, "content": "old"}, cancel))["bytes"] == 3
    tools.execute("file_edit", {"path": path, "old_text": "old", "new_text": "new"}, cancel)
    assert json.loads(tools.execute("file_read", {"path": path}, cancel))["content"] == "new"
    tools.execute("memory_write", {"content": "likes Python"}, cancel)
    assert "likes Python" in str(json.loads(tools.execute("memory_get", {"keywords": "python"}, cancel)))


class FakeClient:
    def __init__(self):
        self.calls = 0

    def complete(self, _messages, _tools, on_text, _cancel):
        self.calls += 1
        if self.calls == 1:
            return {"role": "assistant", "content": "", "tool_calls": [{
                "id": "call_1", "type": "function", "function": {
                    "name": "file_write", "arguments": '{"path":"/var/muselite/workspace/a.txt","content":"hello"}'
                }}]}
        on_text("完成")
        return {"role": "assistant", "content": "完成", "tool_calls": []}


def test_agent_persists_tool_cycle(tmp_path):
    store = Store(tmp_path / "app.db")
    sid = store.create_session()
    sandbox = ProotSandbox(tmp_path / "data", tmp_path / "assets", tmp_path / "lib")
    events = []
    Agent(store, FakeClient(), ToolExecutor(sandbox, None)).run(
        sid, "写文件", lambda name, value: events.append((name, value)))
    assert [m["role"] for m in store.messages(sid)] == ["user", "assistant", "tool", "assistant"]
    assert (sandbox.workspace / "a.txt").read_text() == "hello"
    assert events[-1][0] == "done"


def test_agent_summarizes_when_tool_round_budget_is_exhausted(tmp_path):
    class RepeatingClient:
        def __init__(self):
            self.calls = []

        def complete(self, messages, schemas, on_text, _cancel):
            self.calls.append((len(schemas), messages[0]["content"]))
            if schemas:
                return {"role": "assistant", "content": "", "tool_calls": [{
                    "id": f"call_{len(self.calls)}", "type": "function", "function": {
                        "name": "memory_get", "arguments": "{}"
                    }}]}
            on_text("目前未找到相关记忆，任务尚未完成。")
            return {"role": "assistant", "content": "目前未找到相关记忆，任务尚未完成。",
                    "tool_calls": []}

    store = Store(tmp_path / "app.db")
    sid = store.create_session()
    client = RepeatingClient()
    events = []
    tools = ToolExecutor(DesktopSandbox(tmp_path / "data"), None)
    Agent(store, client, tools, max_steps=2).run(
        sid, "查找记忆", lambda name, value: events.append((name, value)))

    assert len(client.calls) == 3
    assert client.calls[-1][0] == 0
    assert "No tools are available" in client.calls[-1][1]
    assert store.messages(sid)[-1] == {
        "role": "assistant", "content": "目前未找到相关记忆，任务尚未完成。"}
    assert events[-1][0] == "done"
    assert all(name != "error" for name, _ in events)


def test_agent_tool_limit_keeps_a_truthful_fallback_if_model_returns_no_text(tmp_path):
    class NoSummaryClient:
        def complete(self, _messages, schemas, _on_text, _cancel):
            if schemas:
                return {"role": "assistant", "content": "", "tool_calls": [{
                    "id": "call_1", "type": "function", "function": {
                        "name": "memory_get", "arguments": "{}"
                    }}]}
            return {"role": "assistant", "content": "", "tool_calls": []}

    store = Store(tmp_path / "app.db")
    sid = store.create_session()
    tools = ToolExecutor(DesktopSandbox(tmp_path / "data"), None)
    Agent(store, NoSummaryClient(), tools, max_steps=1).run(sid, "查找记忆")
    final = store.messages(sid)[-1]
    assert final["role"] == "assistant"
    assert "尚未完成任务" in final["content"]
    assert "tool_calls" not in final


class FakeBrowserBridge:
    def __init__(self):
        self.calls = []

    def call(self, action, params):
        self.calls.append(action)
        if action == "execute_js":
            return {"result": [{"text": "item one", "html": "<article>item one</article>"}]}
        return {"result": True}


def test_browser_collect_deduplicates_items():
    bridge = FakeBrowserBridge()
    result = BrowserController(bridge).call("scroll_and_collect", {
        "item_selector": "article", "scroll_count": 2, "keywords": ["one"]})
    assert result["count"] == 1
    assert bridge.calls == ["execute_js", "scroll", "execute_js", "scroll"]


def test_browser_collect_requires_selector_and_honors_cancel():
    bridge = FakeBrowserBridge()
    browser = BrowserController(bridge)
    with pytest.raises(ValueError, match="item_selector"):
        browser.call("scroll_and_collect", {})
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(InterruptedError):
        browser.call("navigate", {"url": "https://example.com"}, cancel)
    assert bridge.calls == []


def test_dom_stability_timeout_is_milliseconds():
    class ChangingBridge:
        def call(self, action, params):
            return {"result": {"size": 12, "hash": 1}}

    result = BrowserController(ChangingBridge()).call("wait_for_dom_stable", {"timeout": 800})
    assert result == {"stable": True, "dom_size": 12}


def test_desktop_preview_uses_memory_only_key_and_available_tools(tmp_path):
    bridge = DesktopBridge(tmp_path / "app")
    bridge.save_key("temporary-secret")
    assert bridge.load_key() == "temporary-secret"
    assert DesktopBridge(tmp_path / "app").load_key() == ""
    sandbox = DesktopSandbox(bridge.files_dir)
    executor = ToolExecutor(sandbox, None)
    names = {schema["function"]["name"] for schema in executor.schemas}
    assert "file_write" in names and "memory_get" in names
    assert "shell_execute" not in names and "browser_use" not in names
    path = "/var/muselite/workspace/desktop.txt"
    result = json.loads(executor.execute("file_write", {"path": path, "content": "ok"}, threading.Event()))
    assert result["bytes"] == 2
    assert json.loads(executor.execute("file_read", {"path": path}, threading.Event()))["content"] == "ok"
    with pytest.raises(SandboxError, match="桌面预览只能"):
        sandbox.resolve("/etc/passwd")
    with pytest.raises(SandboxError, match="Android"):
        sandbox.execute("pwd")


def test_desktop_agent_advertises_only_available_tools(tmp_path):
    class CaptureClient:
        def complete(self, messages, schemas, on_text, cancel):
            self.prompt = messages[0]["content"]
            self.names = {schema["function"]["name"] for schema in schemas}
            return {"role": "assistant", "content": "可以聊天", "tool_calls": []}

    store = Store(tmp_path / "app.db")
    client = CaptureClient()
    Agent(store, client, ToolExecutor(DesktopSandbox(tmp_path / "data"), None)).run(
        store.create_session(), "你好")
    assert "desktop preview" in client.prompt
    assert "file_read" in client.names
    assert "shell_execute" not in client.names
    assert "browser_use" not in client.names
