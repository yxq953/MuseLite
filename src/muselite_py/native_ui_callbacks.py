"""Callbacks from the Android native controls into the Python application."""

from __future__ import annotations

import json


_app = None


def bind(app) -> None:
    global _app
    _app = app


def on_action(action: str, payload: str) -> bool:
    if _app is None:
        raise RuntimeError("MuseLite 尚未完成启动")
    data = json.loads(payload)
    if action == "sessions":
        _app.show_sessions()
    elif action == "new":
        _app.new_session()
    elif action == "open":
        _app.open_session(data["id"])
    elif action == "rename":
        _app.rename_session(data["id"], data.get("title", "定时任务"))
    elif action == "start":
        return bool(_app.start_from_home(data.get("text", "")))
    elif action == "send":
        return bool(_app.send(prompt_override=data.get("text", "")))
    elif action == "scheduled_send":
        _app.open_session(data["id"])
        return bool(_app.send(prompt_override=data.get("text", "")))
    elif action == "scheduled_task_fire":
        return bool(_app.trigger_scheduled_task(data["id"]))
    elif action == "tasks":
        _app.show_scheduled_tasks()
    elif action == "task_add":
        _app.show_add_scheduled_task()
    elif action == "task_save":
        return bool(_app.save_scheduled_task(data))
    elif action == "task_toggle":
        return bool(_app.toggle_scheduled_task(data["id"], bool(data["enabled"])))
    elif action == "task_delete":
        return bool(_app.delete_scheduled_task(data["id"]))
    elif action == "stop":
        _app.stop_agent()
    elif action == "settings":
        _app.show_settings()
    elif action == "soul":
        _app.show_agent_soul()
    elif action == "skills":
        _app.show_skills()
    elif action == "skill_open":
        return bool(_app.show_skill(data["name"], data.get("path", "SKILL.md")))
    elif action == "skill_toggle":
        return bool(_app.toggle_skill(data["name"], bool(data["enabled"])))
    elif action == "skill_save":
        return bool(_app.save_skill_file(data))
    elif action == "save_soul":
        return bool(_app.save_native_soul(data))
    elif action == "clear_soul":
        return bool(_app.clear_native_soul())
    elif action == "memory":
        _app.show_memories()
    elif action == "memory_search":
        return bool(_app.memory_search_native(data.get("query", "")))
    elif action == "memory_accept":
        return bool(_app.accept_memory(data["id"]))
    elif action == "memory_delete":
        return bool(_app.delete_memory(data["id"]))
    elif action == "memory_edit":
        return bool(_app.update_memory(data["id"], data.get("content", "")))
    elif action == "memory_clear":
        return bool(_app.clear_memories(True))
    elif action == "memory_export":
        return bool(_app.export_memories())
    elif action == "save_settings":
        return bool(_app.save_native_settings(data))
    elif action == "phone_toggle":
        return bool(_app.set_native_phone_enabled(bool(data.get("enabled"))))
    elif action == "phone_refresh":
        _app.refresh_native_phone_status()
    elif action == "accessibility":
        _app.android.phone_open_settings()
    elif action == "notifications":
        _app.android.phone_request_notifications()
    elif action == "browser":
        _app.show_browser()
    else:
        raise ValueError(f"未知界面操作：{action}")
    return True
