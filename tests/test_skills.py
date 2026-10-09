"""Skills must be discoverable, editable, isolated per request, and usable via chat."""

import base64
import copy
import json
import threading

import pytest

from muselite_py.agent import Agent
from muselite_py.desktop import DesktopSandbox
from muselite_py.skills import SkillManager, parse_skill
from muselite_py.storage import Store
from muselite_py.tools import ToolExecutor


def skill_text(name="meeting-summary", body="Summarize decisions without inventing owners."):
    return f"---\nname: {name}\ndescription: Summarize meeting notes and action items.\n---\n\n{body}\n"


@pytest.fixture
def skills(tmp_path):
    store = Store(tmp_path / "app.db")
    sandbox = DesktopSandbox(tmp_path / "data")
    manager = SkillManager(sandbox, store)
    yield manager
    store.close()


def test_builtin_is_seeded_once_and_user_edits_and_switch_survive_restart(skills):
    assert skills.detail("skill-creator")["enabled"]
    original = skills.read("skill-creator", "SKILL.md")["content"]
    revised = original + "\n用户定制说明。\n"
    skills.save_file("skill-creator", "SKILL.md", revised)
    skills.set_enabled("skill-creator", False)
    reopened = SkillManager(skills.sandbox, skills.store)
    assert reopened.read("skill-creator", "SKILL.md")["content"] == revised
    assert not reopened.detail("skill-creator")["enabled"]


def test_yaml_block_description_and_invalid_edits(skills):
    text = "---\nname: example\ndescription: |\n  会议总结：整理行动项。\n  当用户提供会议记录时使用。\n---\n\n实际说明。\n"
    assert "会议总结" in parse_skill(text)["description"]
    skills.create(text)
    with pytest.raises(ValueError, match="一致"):
        skills.save_file("example", "SKILL.md", text.replace("name: example", "name: other"))
    with pytest.raises(ValueError, match="YAML"):
        skills.save_file("example", "SKILL.md", text.replace("description: |", "description: ["))
    assert skills.read("example", "SKILL.md")["content"] == text


def test_progressive_loading_and_binary_asset_information(skills):
    secret_body = "WORKFLOW_BODY_ONLY_ON_LOAD"
    secret_reference = "REFERENCE_ONLY_ON_READ"
    skills.create(skill_text(body=secret_body), [
        {"path": "references/guide.md", "content": secret_reference},
        {"path": "assets/template.bin", "encoding": "base64",
         "content": base64.b64encode(b"\x00\xff\x01").decode()},
    ])
    snapshot = skills.begin_request()
    try:
        assert "meeting-summary" in snapshot.catalog()
        assert secret_body not in snapshot.catalog()
        with pytest.raises(ValueError, match="skill_load"):
            snapshot.read("meeting-summary", "references/guide.md")
        loaded = snapshot.load("meeting-summary")
        assert secret_body in loaded["instructions"]
        assert secret_reference not in json.dumps(loaded)
        assert snapshot.read("meeting-summary", "references/guide.md")["content"] == secret_reference
        assert snapshot.load("meeting-summary")["already_loaded"]
        assert not skills.read("meeting-summary", "assets/template.bin")["editable"]
        with pytest.raises(ValueError, match="二进制"):
            snapshot.read("meeting-summary", "assets/template.bin")
    finally:
        root = snapshot.root
        snapshot.close()
    assert not root.exists()


def test_request_snapshot_preserves_instructions_resources_and_script_paths(skills):
    skills.create(skill_text(body="OLD_BODY"), [
        {"path": "references/guide.md", "content": "OLD_REFERENCE"},
        {"path": "scripts/run.sh", "content": "echo OLD_SCRIPT\n"},
    ])
    before = skills.begin_request()
    skills.save_file("meeting-summary", "SKILL.md", skill_text(body="NEW_BODY"))
    skills.save_file("meeting-summary", "references/guide.md", "NEW_REFERENCE")
    skills.save_file("meeting-summary", "scripts/run.sh", "echo NEW_SCRIPT\n")
    skills.set_enabled("meeting-summary", False)
    try:
        loaded = before.load("meeting-summary")
        assert "OLD_BODY" in loaded["instructions"]
        assert before.read("meeting-summary", "references/guide.md")["content"] == "OLD_REFERENCE"
        script = skills.sandbox.resolve(loaded["base_path"] + "/scripts/run.sh", must_exist=True)
        assert script.read_text() == "echo OLD_SCRIPT\n"
        after = skills.begin_request()
        try:
            assert "meeting-summary" not in after.items
            with pytest.raises(ValueError, match="未开启"):
                after.load("meeting-summary")
        finally:
            after.close()
        skills.set_enabled("meeting-summary", True)
        next_request = skills.begin_request()
        try:
            assert "NEW_BODY" in next_request.load("meeting-summary")["instructions"]
            assert next_request.read("meeting-summary", "references/guide.md")["content"] == "NEW_REFERENCE"
        finally:
            next_request.close()
    finally:
        before.close()


@pytest.mark.parametrize("path", ["../escape.txt", "/tmp/escape", "scripts/../../escape", "a\\b", "C:/escape", "SKILL.md", "skill.md"])
def test_invalid_creation_is_atomic_and_cannot_overwrite_or_escape(skills, path):
    with pytest.raises(ValueError):
        skills.create(skill_text("invalid-attempt"), [{"path": path, "content": "bad"}])
    assert not (skills.root / "invalid-attempt").exists()
    assert not any(p.name.startswith(".create-") for p in skills.root.iterdir())


def test_duplicate_creation_leaves_original_intact(skills):
    skills.create(skill_text())
    skills.set_enabled("meeting-summary", False)
    with pytest.raises(ValueError, match="同名"):
        skills.create(skill_text(body="replacement"))
    assert "replacement" not in skills.read("meeting-summary", "SKILL.md")["content"]
    assert not skills.enabled("meeting-summary")


def test_invalid_skill_remains_visible_for_repair_and_is_not_loaded(skills):
    skills.create(skill_text())
    (skills.root / "meeting-summary" / "SKILL.md").write_text("invalid yaml", encoding="utf-8")
    assert skills.detail("meeting-summary")["error"]
    skills.set_enabled("meeting-summary", False)
    with pytest.raises(ValueError, match="修正"):
        skills.set_enabled("meeting-summary", True)
    snapshot = skills.begin_request()
    try:
        assert "meeting-summary" not in snapshot.items
    finally:
        snapshot.close()
    skills.save_file("meeting-summary", "SKILL.md", skill_text())
    skills.set_enabled("meeting-summary", True)
    assert skills.detail("meeting-summary")["enabled"]


def tool_call(name, args, index):
    return {"id": f"call_{index}", "type": "function", "function": {
        "name": name, "arguments": json.dumps(args)}}


def test_chat_creator_creates_and_uses_new_skill_in_same_request(skills):
    class Client:
        def __init__(self):
            self.calls = []

        def complete(self, messages, schemas, on_text, cancel):
            self.calls.append(copy.deepcopy(messages))
            step = len(self.calls)
            if step == 1:
                assert "# Skill Creator" not in messages[0]["content"]
                call = tool_call("skill_load", {"name": "skill-creator"}, step)
            elif step == 2:
                assert "# Skill Creator" in json.loads(messages[-1]["content"])["instructions"]
                call = tool_call("skill_create", {"content": skill_text(body="NEW_WORKFLOW"),
                    "files": [{"path": "references/output.md", "content": "ACTION_ITEMS"}]}, step)
            elif step == 3:
                assert json.loads(messages[-1]["content"])["created"]
                assert "meeting-summary" in messages[0]["content"]
                call = tool_call("skill_load", {"name": "meeting-summary"}, step)
            elif step == 4:
                assert "NEW_WORKFLOW" in json.loads(messages[-1]["content"])["instructions"]
                call = tool_call("skill_read", {"name": "meeting-summary", "path": "references/output.md"}, step)
            else:
                assert json.loads(messages[-1]["content"])["content"] == "ACTION_ITEMS"
                on_text("已创建并使用会议总结技能。")
                return {"role": "assistant", "content": "已创建并使用会议总结技能。", "tool_calls": []}
            return {"role": "assistant", "content": "", "tool_calls": [call]}

    executor = ToolExecutor(skills.sandbox, None, store=skills.store, skills=skills)
    client = Client()
    sid = skills.store.create_session()
    events = []
    Agent(skills.store, client, executor).run(sid, "创建一个会议总结技能并立即使用它",
                                            lambda name, value: events.append((name, value)))
    assert events[-1][0] == "done"
    assert skills.detail("meeting-summary")["enabled"]
    assert executor.skill_snapshot is None
    assert not list((skills.sandbox.workspace / ".skill-runs").iterdir())

    skills.set_enabled("meeting-summary", False)
    skills.set_enabled("skill-creator", False)

    class NextClient:
        def complete(self, messages, schemas, on_text, cancel):
            # The full original tool transcript remains stored, but stale skill
            # bodies must not be sent to the model on subsequent requests.
            assert all("NEW_WORKFLOW" not in m.get("content", "") for m in messages
                       if m["role"] == "tool")
            assert "NEW_WORKFLOW" not in json.dumps(messages, ensure_ascii=False)
            assert "skill_create" not in {s["function"]["name"] for s in schemas}
            assert "<available_skills>" not in messages[0]["content"]
            return {"role": "assistant", "content": "技能已关闭", "tool_calls": []}

    Agent(skills.store, NextClient(), executor).run(sid, "继续")
    assert "NEW_WORKFLOW" in "\n".join(m["content"] for m in skills.store.messages(sid) if m["role"] == "tool")


def test_explicit_skill_loads_before_model_and_disabled_skill_is_rejected(skills):
    skills.create(skill_text(body="EXPLICIT_WORKFLOW"))

    class Client:
        def __init__(self):
            self.messages = []

        def complete(self, messages, schemas, on_text, cancel):
            self.messages = copy.deepcopy(messages)
            return {"role": "assistant", "content": "完成", "tool_calls": []}

    sid = skills.store.create_session()
    executor = ToolExecutor(skills.sandbox, None, store=skills.store, skills=skills)
    client = Client()
    agent = Agent(skills.store, client, executor)
    agent.run(sid, "$meeting-summary 整理以下内容")
    assert any("EXPLICIT_WORKFLOW" in m["content"] for m in client.messages if m["role"] == "system")
    skills.set_enabled("meeting-summary", False)
    agent.run(sid, "$meeting-summary 再次整理")
    assert all("EXPLICIT_WORKFLOW" not in m["content"] for m in client.messages if m["role"] == "system")
    assert any("未开启" in m["content"] for m in client.messages if m["role"] == "system")


def test_creator_must_be_loaded_and_disabled_creator_hides_creation_tool(skills):
    executor = ToolExecutor(skills.sandbox, None, store=skills.store, skills=skills)
    cancel = threading.Event()
    executor.begin_request("创建技能")
    assert "error" in json.loads(executor.execute("skill_create", {"content": skill_text()}, cancel))
    executor.end_request()
    skills.set_enabled("skill-creator", False)
    executor.begin_request("创建技能")
    try:
        assert "skill_create" not in {s["function"]["name"] for s in executor.schemas}
        assert "error" in json.loads(executor.execute("skill_load", {"name": "skill-creator"}, cancel))
    finally:
        executor.end_request()


def test_native_management_callbacks_edit_and_toggle_real_files(skills):
    from muselite_py import native_ui_callbacks
    from muselite_py.toga_ui import MuseLiteApp

    class Bridge:
        def __init__(self):
            self.states = []

        def ui_show(self, state):
            self.states.append(state)

        def ui_status(self, text, error):
            pass

    app = object.__new__(MuseLiteApp)
    app.skills = skills
    app.is_android = True
    app.android = Bridge()
    app.last_status = ""
    app.status_error = False
    native_ui_callbacks.bind(app)
    try:
        assert native_ui_callbacks.on_action("skills", "{}")
        assert app.android.states[-1]["view"] == "skills"
        assert native_ui_callbacks.on_action("skill_open", json.dumps({"name": "skill-creator"}))
        assert app.android.states[-1]["file"]["editable"]
        new_text = skills.read("skill-creator", "SKILL.md")["content"] + "\nEDITED_IN_UI\n"
        assert native_ui_callbacks.on_action("skill_save", json.dumps({"name": "skill-creator",
            "path": "SKILL.md", "content": new_text}))
        assert "EDITED_IN_UI" in skills.read("skill-creator", "SKILL.md")["content"]
        assert not native_ui_callbacks.on_action("skill_save", json.dumps({"name": "skill-creator",
            "path": "SKILL.md", "content": "bad metadata"}))
        assert app.status_error
        assert native_ui_callbacks.on_action("skill_toggle", json.dumps({"name": "skill-creator", "enabled": False}))
        assert not skills.detail("skill-creator")["enabled"]
    finally:
        native_ui_callbacks.bind(None)
