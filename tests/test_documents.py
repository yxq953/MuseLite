import json
import threading

import pytest

from muselite_py.agent import Agent
from muselite_py.desktop import DesktopSandbox
from muselite_py.documents import DocumentController, MAX_DOCUMENT_BYTES
from muselite_py.storage import Store
from muselite_py.tools import ToolExecutor


class FolderBridge:
    def __init__(self, configured=True):
        self.configured = configured
        self.calls = []

    def documents_call(self, action, params):
        self.calls.append((action, params))
        if action == "status":
            return {"configured": self.configured, "path": "/storage/emulated/0/Documents/MuseLite"}
        if not self.configured:
            raise RuntimeError("请在设置 > 文档保存目录中选择文件夹")
        if action == "list":
            return {"entries": [{"name": "notes.md", "path": "报告/notes.md", "directory": False}],
                    "total": 1, "has_more": False, "next_offset": None}
        if action == "read":
            if params["path"] == "missing.md":
                raise RuntimeError("文件或文件夹不存在：missing.md")
            return {"content": "# 笔记\n" if params["offset"] == 0 else "中文 😀",
                    "truncated": params["offset"] == 0,
                    "next_offset": 5 if params["offset"] == 0 else None}
        if "source_file" in params:
            from pathlib import Path
            self.exported = Path(params["source_file"]).read_bytes()
        else:
            self.exported = params["content"].encode("utf-8")
        return {"saved": True, "path": "/storage/emulated/0/Documents/MuseLite/" + params["path"],
                "bytes": len(self.exported)}


def executor(tmp_path, configured=True):
    sandbox = DesktopSandbox(tmp_path / "data")
    bridge = FolderBridge(configured)
    tools = ToolExecutor(sandbox, None, documents=DocumentController(bridge, sandbox))
    return tools, bridge


def test_utf8_text_and_binary_export(tmp_path):
    tools, bridge = executor(tmp_path)
    cancel = threading.Event()
    result = json.loads(tools.execute("document_save", {"path": "报告/总结.md", "content": "# 总结\n中文 😀"}, cancel))
    assert result["saved"] and result["bytes"] == len("# 总结\n中文 😀".encode("utf-8"))
    tools.execute("file_write", {"path": "/var/muselite/workspace/export.pdf", "content": ""}, cancel)
    source = tools.sandbox.resolve("/var/muselite/workspace/export.pdf", must_exist=True)
    source.write_bytes(b"%PDF-1.7\n\x00\xff")
    result = json.loads(tools.execute("document_save", {
        "path": "export.pdf", "source_path": "/var/muselite/workspace/export.pdf"}, cancel))
    assert result["saved"]
    assert bridge.exported == b"%PDF-1.7\n\x00\xff"


@pytest.mark.parametrize("path", ["/sdcard/a.md", "../a.md", "a/../b.md", "a//b.md", "a/", "a\\b", "C:/a.md", "a\x00.md", ".", ""])
def test_invalid_destinations_never_reach_android(tmp_path, path):
    tools, bridge = executor(tmp_path)
    result = json.loads(tools.execute("document_save", {"path": path, "content": "text"}, threading.Event()))
    assert "error" in result and bridge.calls == []


@pytest.mark.parametrize("extra", [{}, {"content": "", "source_path": "/var/muselite/workspace/a"},
                                   {"content": None}, {"source_path": "/outside/a"},
                                   {"source_path": "/var/muselite/workspace/../secret"}])
def test_invalid_payloads_and_source_escape(tmp_path, extra):
    tools, bridge = executor(tmp_path)
    result = json.loads(tools.execute("document_save", {"path": "a.md", **extra}, threading.Event()))
    assert "error" in result and bridge.calls == []


def test_size_limit_and_stop_prevent_export(tmp_path):
    tools, bridge = executor(tmp_path)
    cancel = threading.Event()
    result = json.loads(tools.execute("document_save", {
        "path": "huge.md", "content": "中" * (MAX_DOCUMENT_BYTES // 3 + 1)}, cancel))
    assert "25 MB" in result["error"] and bridge.calls == []
    cancel.set()
    with pytest.raises(InterruptedError):
        tools.execute("document_save", {"path": "a.md", "content": "text"}, cancel)
    assert bridge.calls == []


def test_directory_permission_errors_and_desktop_availability(tmp_path):
    tools, bridge = executor(tmp_path, configured=False)
    assert not json.loads(tools.execute("document_directory", {}, threading.Event()))["configured"]
    result = json.loads(tools.execute("document_save", {"path": "a.md", "content": "text"}, threading.Event()))
    assert "选择文件夹" in result["error"] and "saved" not in result
    names = {item["function"]["name"] for item in tools.schemas}
    document_tools = {"document_directory", "document_save", "document_list", "document_read"}
    assert document_tools <= names
    desktop = ToolExecutor(tools.sandbox, None)
    assert not document_tools & {item["function"]["name"] for item in desktop.schemas}
    for name in ("document_list", "document_read"):
        result = json.loads(tools.execute(name, {"path": "notes.md"}, threading.Event()))
        assert "选择文件夹" in result["error"] and "content" not in result


def test_agent_document_export_is_persisted(tmp_path):
    tools, bridge = executor(tmp_path)
    store = Store(tmp_path / "app.db")
    sid = store.create_session()

    class Client:
        def __init__(self):
            self.count = 0

        def complete(self, messages, schemas, on_text, cancel):
            self.count += 1
            if self.count == 1:
                return {"role": "assistant", "content": "", "tool_calls": [{
                    "id": "save_1", "type": "function", "function": {
                        "name": "document_save", "arguments": json.dumps({"path": "notes.md", "content": "# 笔记"})}}]}
            result = json.loads(messages[-1]["content"])
            assert result["saved"] and result["path"].endswith("notes.md")
            return {"role": "assistant", "content": "已保存：" + result["path"], "tool_calls": []}

    Agent(store, Client(), tools).run(sid, "把笔记保存到手机文件夹")
    messages = store.messages(sid)
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert bridge.exported.decode("utf-8") == "# 笔记"
    store.close()


def test_phone_folder_list_and_read_forward_pagination(tmp_path):
    tools, bridge = executor(tmp_path)
    cancel = threading.Event()
    tools.execute("document_list", {}, cancel)
    tools.execute("document_list", {"path": "报告", "offset": 200, "limit": 200}, cancel)
    result = json.loads(tools.execute("document_read", {"path": "报告/notes.md"}, cancel))
    assert result["truncated"] and result["content"] == "# 笔记\n"
    result = json.loads(tools.execute("document_read", {
        "path": "报告/notes.md", "offset": 5, "max_chars": 50000}, cancel))
    assert result["content"] == "中文 😀" and not result["truncated"]
    assert bridge.calls == [
        ("list", {"path": "", "offset": 0, "limit": 100}),
        ("list", {"path": "报告", "offset": 200, "limit": 200}),
        ("read", {"path": "报告/notes.md", "offset": 0, "max_chars": 12000}),
        ("read", {"path": "报告/notes.md", "offset": 5, "max_chars": 50000}),
    ]


@pytest.mark.parametrize("name", ["document_list", "document_read"])
@pytest.mark.parametrize("path", ["../a", "/sdcard/a", "a/../b", "a//b", "a/ /b", "a\\b", "a\x00", None, 7])
def test_invalid_read_paths_never_reach_phone(tmp_path, name, path):
    tools, bridge = executor(tmp_path)
    result = json.loads(tools.execute(name, {"path": path}, threading.Event()))
    assert "error" in result and bridge.calls == []


@pytest.mark.parametrize("name,args", [
    ("document_read", {}), ("document_read", {"path": ""}),
    ("document_list", {"offset": -1}), ("document_read", {"offset": 2147483648}),
    ("document_list", {"limit": 201}), ("document_list", {"limit": 0}),
    ("document_read", {"max_chars": 50001}), ("document_read", {"max_chars": 0}),
    ("document_read", {"offset": True}), ("document_list", {"limit": "100"}),
    ("document_read", {"max_chars": 1.5}),
])
def test_invalid_read_options(tmp_path, name, args):
    tools, bridge = executor(tmp_path)
    payload = args if args == {} or "path" in args else {"path": "notes.md", **args}
    result = json.loads(tools.execute(name, payload, threading.Event()))
    assert "error" in result and bridge.calls == []


def test_read_errors_and_cancellation(tmp_path):
    tools, bridge = executor(tmp_path)
    cancel = threading.Event()
    result = json.loads(tools.execute("document_read", {"path": "missing.md"}, cancel))
    assert "不存在" in result["error"] and "content" not in result
    bridge.calls.clear()
    cancel.set()
    for name in ("document_list", "document_read"):
        with pytest.raises(InterruptedError):
            tools.execute(name, {"path": "notes.md"}, cancel)
    assert bridge.calls == []


def test_agent_lists_and_reads_all_pages_and_persists_results(tmp_path):
    tools, bridge = executor(tmp_path)
    store = Store(tmp_path / "app.db")
    sid = store.create_session()

    class Client:
        def __init__(self):
            self.count = 0

        def complete(self, messages, schemas, on_text, cancel):
            self.count += 1
            if self.count == 1:
                name, args = "document_list", {"path": "报告"}
            elif self.count == 2:
                listing = json.loads(messages[-1]["content"])
                name, args = "document_read", {"path": listing["entries"][0]["path"]}
            elif self.count == 3:
                page = json.loads(messages[-1]["content"])
                assert page["truncated"]
                name, args = "document_read", {"path": "报告/notes.md", "offset": page["next_offset"]}
            else:
                page = json.loads(messages[-1]["content"])
                assert not page["truncated"] and page["content"] == "中文 😀"
                return {"role": "assistant", "content": "已读取全文：# 笔记\n中文 😀", "tool_calls": []}
            return {"role": "assistant", "content": "", "tool_calls": [{
                "id": f"doc_{self.count}", "type": "function", "function": {
                    "name": name, "arguments": json.dumps(args)}}]}

    Agent(store, Client(), tools).run(sid, "读取手机目录里的报告/notes.md")
    messages = store.messages(sid)
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant", "tool", "assistant", "tool", "assistant"]
    assert [action for action, _ in bridge.calls] == ["list", "read", "read"]
    assert messages[-1]["content"].endswith("中文 😀")
    store.close()
