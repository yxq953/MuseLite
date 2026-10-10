"""Chaquopy access to the small Java Android bridge used by the Python app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AndroidBridge:
    def __init__(self, activity):
        from java import jclass

        self.activity = activity
        self.native = jclass("com.muselite.python.NativeBridge")
        self.secrets = jclass("com.muselite.python.SecretStore")
        self.phone = jclass("com.muselite.python.PhoneBridge")
        self.ui = jclass("com.muselite.python.NativeUi")
        self.alarms = jclass("com.muselite.python.SessionAlarmScheduler")
        self.calendar = jclass("com.muselite.python.CalendarBridge")
        self.location = jclass("com.muselite.python.LocationBridge")
        self.documents = jclass("com.muselite.python.DocumentBridge")
        self.clipboard = jclass("com.muselite.python.ClipboardBridge")
        self.reply_hint = jclass("com.muselite.python.ReplyHintBridge")

    def reply_hint_call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        request = json.dumps({"action": action, "params": params}, ensure_ascii=False)
        response = json.loads(str(self.reply_hint.call(self.activity, request)))
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def clipboard_call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        request = json.dumps({"action": action, "params": params}, ensure_ascii=False)
        response = json.loads(str(self.clipboard.call(self.activity, request)))
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def documents_call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        request = json.dumps({"action": action, "params": params}, ensure_ascii=False)
        response = json.loads(str(self.documents.call(self.activity, request)))
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def schedule_task(self, task: dict[str, Any]) -> None:
        self.alarms.scheduleTask(self.activity, task["id"], task["when_ms"],
                                 bool(task["repeat_daily"]))

    def cancel_task(self, task_id: str) -> None:
        self.alarms.cancelTask(self.activity, task_id)

    @property
    def files_dir(self) -> Path:
        return Path(str(self.native.filesDir(self.activity)))

    @property
    def native_lib_dir(self) -> Path:
        return Path(str(self.native.nativeLibraryDir(self.activity)))

    def dns_config(self) -> str:
        return str(self.native.dnsConfig(self.activity))

    def stage_asset(self, name: str, destination: Path) -> None:
        self.native.copyAsset(self.activity, name, str(destination))

    def call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        request = json.dumps({"action": action, "params": params}, ensure_ascii=False)
        result = json.loads(str(self.native.call(self.activity, request)))
        if "error" in result:
            raise RuntimeError(result["error"])
        return result

    def save_key(self, value: str) -> None:
        self.secrets.put(self.activity, "provider_api_key", value)

    def load_key(self) -> str:
        return str(self.secrets.get(self.activity, "provider_api_key"))

    def phone_call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        request = json.dumps({"action": action, "params": params}, ensure_ascii=False)
        response = json.loads(str(self.phone.call(self.activity, request)))
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def phone_status(self) -> dict[str, Any]:
        return json.loads(str(self.phone.status(self.activity)))

    def phone_set_enabled(self, enabled: bool) -> None:
        self.phone.setEnabled(self.activity, enabled)

    def phone_open_settings(self) -> None:
        self.phone.openAccessibilitySettings(self.activity)

    def phone_request_notifications(self) -> None:
        self.phone.requestNotifications(self.activity)

    def phone_start_task(self) -> None:
        self.phone.startTask(self.activity)

    def phone_stop_task(self) -> None:
        self.phone.stopTask(self.activity)

    def phone_stop_requested(self) -> bool:
        return bool(self.phone.stopRequested())

    def ui_show(self, state: dict[str, Any]) -> None:
        self.ui.show(self.activity, json.dumps(state, ensure_ascii=False))

    def ui_chat(self, state: dict[str, Any]) -> None:
        self.ui.updateChat(self.activity, json.dumps(state, ensure_ascii=False))

    def ui_status(self, message: str, error: bool = False) -> None:
        self.ui.status(message, error)

    def ui_busy(self, busy: bool) -> None:
        self.ui.busy(busy)

    def ui_model_status(self, available: bool) -> None:
        self.ui.modelStatus(self.activity, available)

    def calendar_call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        request = json.dumps({"action": action, "params": params}, ensure_ascii=False)
        response = json.loads(str(self.calendar.call(self.activity, request)))
        if "error" in response:
            raise RuntimeError(response["error"])
        return response.get("result", response)

    def location_call(self, action: str = "get", params: dict[str, Any] | None = None) -> dict[str, Any]:
        request = json.dumps({"action": action, "params": params or {}}, ensure_ascii=False)
        response = json.loads(str(self.location.call(self.activity, request)))
        if "error" in response:
            raise RuntimeError(response["error"])
        return response.get("result", response)

    def ui_phone_status(self, state: dict[str, Any]) -> None:
        self.ui.phoneState(json.dumps(state, ensure_ascii=False))
