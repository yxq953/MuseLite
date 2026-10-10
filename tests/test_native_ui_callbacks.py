"""The Android controls must deliver typed prompts to the Python agent."""

import json

from muselite_py import native_ui_callbacks


class AppStub:
    def __init__(self):
        self.calls = []

    def start_from_home(self, text):
        self.calls.append(("start", text))
        return True

    def send(self, prompt_override):
        self.calls.append(("send", prompt_override))
        return True

    def open_session(self, session_id):
        self.calls.append(("open", session_id))

    def show_sessions(self):
        self.calls.append(("sessions",))

    def request_chat_reply(self, data):
        self.calls.append(("chat_hint_reply", data))
        return True

    def close_chat_hint(self, data):
        self.calls.append(("chat_hint_close", data))
        return True


def test_native_actions_forward_the_prompt_and_session():
    app = AppStub()
    native_ui_callbacks.bind(app)

    assert native_ui_callbacks.on_action("start", json.dumps({"text": "第一条消息"}))
    assert native_ui_callbacks.on_action("send", json.dumps({"text": "第二条消息"}))
    assert native_ui_callbacks.on_action("open", json.dumps({"id": "session-1"}))
    assert native_ui_callbacks.on_action("sessions", "{}")
    assert app.calls == [
        ("start", "第一条消息"),
        ("send", "第二条消息"),
        ("open", "session-1"),
        ("sessions",),
    ]


def test_floating_reply_click_and_close_preserve_session_tokens():
    app = AppStub()
    native_ui_callbacks.bind(app)
    click = {"session_id": "session-1", "token": "hint-1", "request_id": "click-1"}
    assert native_ui_callbacks.on_action("chat_hint_reply", json.dumps(click))
    assert native_ui_callbacks.on_action("chat_hint_close", '{"token":"hint-1"}')
    assert app.calls == [("chat_hint_reply", click), ("chat_hint_close", {"token": "hint-1"})]
