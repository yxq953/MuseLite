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
