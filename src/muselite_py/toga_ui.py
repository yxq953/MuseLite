"""Python application logic with a native Android UI and a Toga desktop preview."""

from __future__ import annotations

from datetime import datetime
import json
import threading
import time

import toga
from toga.style import Pack

from .agent import Agent
from .android_bridge import AndroidBridge
from .browser import BrowserController
from .chat_view import render_markdown, render_messages, render_page
from .desktop import DesktopBridge, DesktopSandbox
from .provider import OpenAICompatibleClient, ProviderConfig
from .phone import PhoneController
from .sandbox import ProotSandbox
from .storage import Store
from .tools import ToolExecutor


INK = "#173d44"
MUTED = "#668086"
CANVAS = "#f6f5f1"
WHITE = "#ffffff"
ACCENT = "#17656d"
LINE = "#e1e9e6"
ERROR = "#b1473b"


def label(text: str, *, size=13, color=INK, weight="normal", flex=0, margin=0):
    return toga.Label(text, style=Pack(font_size=size, color=color,
                                       font_weight=weight, flex=flex, margin=margin))


def button(caption: str, handler, *, flex=0, width=None, height=44):
    dimensions = {"flex": flex, "height": height}
    if width is not None:
        dimensions["width"] = width
    return toga.Button(caption, on_press=lambda _widget: handler(),
                       style=Pack(**dimensions))


def display_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item.get("text", "")) for item in content
                         if isinstance(item, dict) and item.get("type") == "text")
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def browser_progress_text(event: dict) -> str:
    """Turn an in-flight browser result into a compact live tool transcript."""
    labels = {
        "navigate": "打开网页",
        "get_readable": "读取网页正文",
        "get_text": "读取网页文本",
        "get_page_info": "读取网页信息",
        "find_elements": "查找可交互元素",
        "click": "点击网页元素",
        "type": "输入网页内容",
        "scroll": "滚动网页",
        "scroll_and_collect": "滚动并收集内容",
        "screenshot": "获取网页截图",
        "execute_js": "执行网页脚本",
        "wait_for_dom_stable": "等待网页稳定",
        "fetch": "读取网页资源",
    }
    action = str(event.get("action", "browser_use"))
    label_text = labels.get(action, action)
    if event.get("phase") == "start":
        return "浏览器 · " + label_text + "…"
    result = event.get("result")
    if not isinstance(result, dict):
        return "浏览器 · " + label_text + "\n" + str(result or "已完成")
    lines = []
    title = result.get("title")
    url = result.get("url")
    if title:
        lines.append("标题：" + str(title))
    if url:
        lines.append("地址：" + str(url))
    readable = result.get("text")
    if isinstance(readable, str) and readable.strip():
        lines.append(readable.strip())
    items = result.get("items")
    if isinstance(items, list) and items:
        for item in items[:8]:
            if isinstance(item, dict) and item.get("text"):
                lines.append("• " + str(item["text"]).strip())
    if not lines:
        summary = json.dumps(result, ensure_ascii=False, separators=(", ", ": "))
        lines.append(summary)
    return "浏览器 · " + label_text + "\n" + "\n".join(lines)[:3200]


class MuseLiteApp(toga.App):
    def startup(self):
        self.is_android = toga.platform.current_platform == "android"
        self.android = (AndroidBridge(self._impl.native) if self.is_android
                        else DesktopBridge())
        self.home = self.android.files_dir
        self.store = Store(self.home / "muselite.sqlite3")
        self.startup_error = None
        if self.is_android:
            self.sandbox = ProotSandbox(self.home, self.home / "assets",
                                        self.android.native_lib_dir,
                                        self.android.dns_config)
            try:
                self.android.stage_asset("alpine-minirootfs.tar",
                                         self.sandbox.assets_dir / "alpine-minirootfs.tar")
                self.android.call("configure", {"workspace": str(self.sandbox.workspace)})
            except Exception as exc:
                self.startup_error = str(exc)
            self.browser = BrowserController(
                self.android,
                on_show=lambda: self.android.call("show_browser", {"visible": True}),
                on_preview=lambda event: self._update_browser_preview(event),
            )
        else:
            self.sandbox = DesktopSandbox(self.home)
            self.browser = None

        self.current_session = None
        self._pending_scheduled_tasks: list[str] = []
        self._scheduled_session_ids: set[str] = set()
        self.current_view = "sessions"
        self.active_agent = None
        self.phone_active = False
        self.busy = False
        self.display_messages: list[dict] = []
        self._stream_index: int | None = None
        self._render_handle = None
        self._transcript_ready = False
        self._last_full_render = 0.0
        self.transcript = None
        self.native_transcript = None
        self.native_transcript_box = None
        self.transcript_host = None
        self.last_status = ""
        self.status_error = False
        self.root = toga.Box(style=Pack(direction="column", background_color=CANVAS))
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = self.root
        if self.is_android:
            from .native_ui_callbacks import bind

            bind(self)
            self.main_window.show()
            self.show_sessions()
        else:
            self.show_sessions()
            self.main_window.show()

    def _native_sessions_state(self) -> dict:
        return {
            "view": "sessions", "title": "MuseLite", "subtitle": "你的智能工作空间",
            "status": self.last_status, "status_error": self.status_error,
            "sessions": [
                {"id": item["id"], "title": item["title"] or "新对话",
                 "updated": datetime.fromtimestamp(item["updated_at"]).strftime("%m月%d日 %H:%M")}
                for item in self.store.sessions()
                if self.store.messages(item["id"])
            ],
        }

    def _native_chat_state(self) -> dict:
        session = next((item for item in self.store.sessions()
                        if item["id"] == self.current_session), None)
        messages = []
        for item in self.display_messages[-80:]:
            text = str(item.get("content") or "")[:8000]
            entry = {"role": item.get("role", "assistant"), "content": text,
                     "pending": bool(item.get("pending")), "name": item.get("name", "工具")}
            if entry["role"] == "assistant" and text:
                entry["html"] = render_markdown(text)
            messages.append(entry)
        return {
            "view": "chat", "title": ((session or {}).get("title") or "新对话")[:28],
            "subtitle": "模型 · " + self.store.get_setting("model", "deepseek-flash"),
            "session_id": self.current_session or "",
            "messages": messages, "busy": self.busy,
            "status": self.last_status, "status_error": self.status_error,
        }

    def _native_settings_state(self) -> dict:
        try:
            phone_state = self.android.phone_status()
        except Exception as exc:
            phone_state = {"enabled": False, "service": False, "notifications": False}
            self.last_status = str(exc)
            self.status_error = True
        return {
            "view": "settings", "title": "设置", "subtitle": "模型与手机操作",
            "base_url": self.store.get_setting("base_url", "https://api.deepseek.com"),
            "model": self.store.get_setting("model", "deepseek-flash"),
            "vision": self.store.get_setting("vision", "1") == "1",
            "phone": phone_state,
            "status": self.last_status, "status_error": self.status_error,
        }

    def _native_tasks_state(self) -> dict:
        return {
            "view": "tasks", "title": "定时任务", "subtitle": "管理自动执行的任务",
            "tasks": [
                {**task, "time_label": datetime.fromtimestamp(task["when_ms"] / 1000)
                 .strftime("%H:%M" if task["repeat_daily"] else "%Y-%m-%d %H:%M")}
                for task in self.store.scheduled_tasks()
            ],
        }

    def show_scheduled_tasks(self):
        self.current_view = "tasks"
        if self.is_android:
            self.android.ui_show(self._native_tasks_state())

    def show_add_scheduled_task(self):
        self.current_view = "task_add"
        if self.is_android:
            self.android.ui_show({"view": "task_add", "title": "添加定时任务",
                                  "subtitle": "设置执行时间和任务要求"})

    def save_scheduled_task(self, data: dict) -> bool:
        try:
            task = self.store.create_scheduled_task(
                str(data.get("name", "")), str(data.get("prompt", "")),
                int(data["when_ms"]), bool(data.get("repeat_daily")))
            try:
                self.android.schedule_task(task)
            except Exception:
                self.store.delete_scheduled_task(task["id"])
                raise
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return False
        self.show_scheduled_tasks()
        return True

    def toggle_scheduled_task(self, task_id: str, enabled: bool) -> bool:
        task = self.store.scheduled_task(task_id)
        if task is None:
            return False
        try:
            if enabled:
                if not task["repeat_daily"] and task["when_ms"] <= int(time.time() * 1000):
                    raise ValueError("一次性任务的时间已过，请重新添加")
                self.android.schedule_task(task)
            else:
                self.android.cancel_task(task_id)
            self.store.set_scheduled_task_enabled(task_id, enabled)
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return False
        self.show_scheduled_tasks()
        return True

    def delete_scheduled_task(self, task_id: str) -> bool:
        if self.store.scheduled_task(task_id) is None:
            return False
        self.android.cancel_task(task_id)
        self.store.delete_scheduled_task(task_id)
        self.show_scheduled_tasks()
        return True

    def trigger_scheduled_task(self, task_id: str) -> bool:
        task = self.store.scheduled_task(task_id)
        if task is None or not task["enabled"]:
            return False
        if self.busy:
            if task_id not in self._pending_scheduled_tasks:
                self._pending_scheduled_tasks.append(task_id)
            return True
        sid = self.store.create_session(task["name"])
        self.open_session(sid)
        if not self.send(prompt_override=task["prompt"]):
            self.store.delete_session(sid)
            return False
        self._scheduled_session_ids.add(sid)
        self.store.mark_scheduled_task_triggered(task_id)
        return True

    def _cleanup_empty_sessions(self) -> None:
        """Remove draft sessions which were opened but never used."""
        for session in self.store.sessions():
            if self.store.messages(session["id"]):
                continue
            if session["id"] in self._scheduled_session_ids:
                continue
            # A scheduled task is intentionally allowed to have no chat messages yet.
            if (session.get("title") or "").strip() == "定时任务":
                continue
            self.store.delete_session(session["id"])
        if self.current_session and not self.store.messages(self.current_session):
            current = next((s for s in self.store.sessions()
                            if s["id"] == self.current_session), None)
            if current is None:
                self.current_session = None
                self.display_messages = []

    def _screen(self, title: str, subtitle: str = ""):
        self.root.clear()
        heading = toga.Box(style=Pack(direction="column", background_color=CANVAS))
        top = toga.Box(style=Pack(direction="row", gap=7, margin=10, height=47))
        top.add(button("会话", self.show_sessions, width=58, height=42))
        titles = toga.Box(style=Pack(direction="column", flex=1, gap=2, margin_top=2))
        titles.add(label(title, size=19, weight="bold", flex=1))
        if subtitle:
            titles.add(label(subtitle, size=11, color=MUTED))
        top.add(titles)
        top.add(button("设置", self.show_settings, width=58, height=42))
        heading.add(top)
        heading.add(toga.Box(style=Pack(height=1, background_color=LINE)))
        self.root.add(heading)
        body = toga.Box(style=Pack(direction="column", flex=1,
                                   background_color=CANVAS))
        self.root.add(body)
        self.status_label = label(self.last_status, size=11,
                                  color=ERROR if self.last_status else MUTED, margin=6)
        self.root.add(self.status_label)
        if self.startup_error:
            self._set_status("Android 资源错误：" + self.startup_error, error=True)
        return body

    def _set_status(self, text: str, *, error=False):
        self.last_status = text
        self.status_error = error
        if self.is_android:
            self.android.ui_status(text, error)
        else:
            self.status_label.text = text
            self.status_label.style.color = ERROR if error else MUTED

    def show_sessions(self):
        self._cleanup_empty_sessions()
        self.current_view = "sessions"
        if self.is_android:
            self.android.ui_show(self._native_sessions_state())
            return
        content = self._screen("MuseLite", "你的智能工作空间")
        intro = toga.Box(style=Pack(direction="column", gap=5, margin=14,
                                    background_color=ACCENT))
        intro.add(label("✦  MuseLite Python", size=19, color=WHITE,
                        weight="bold", margin=14))
        intro.add(label("想法、对话和工具，都在这里。", size=13,
                        color="#dcefeb", margin=(0, 14, 14, 14)))
        content.add(intro)
        new = toga.Box(style=Pack(direction="column", margin=(0, 14, 10, 14)))
        new.add(button("定时任务" if self.is_android else "开始新对话",
                       self.show_scheduled_tasks if self.is_android else self.new_session,
                       height=50))
        content.add(new)
        quick = toga.Box(style=Pack(direction="column", gap=6, margin=(0, 14, 12, 14),
                                    background_color=WHITE))
        quick.add(label("直接开始", size=12, color=MUTED, weight="bold",
                        margin=(10, 10, 0, 10)))
        quick_row = toga.Box(style=Pack(direction="row", gap=8, height=82,
                                        margin=(0, 10, 10, 10)))
        self.home_input = toga.MultilineTextInput(
            placeholder="输入问题或任务，发送后自动创建对话…",
            style=Pack(flex=1, height=78))
        quick_row.add(self.home_input)
        self.home_send_button = button("发送", self.start_from_home,
                                       width=78, height=78)
        self.home_send_button.enabled = not self.busy
        quick_row.add(self.home_send_button)
        quick.add(quick_row)
        content.add(quick)
        sessions = [s for s in self.store.sessions() if self.store.messages(s["id"])]
        list_box = toga.Box(style=Pack(direction="column", gap=8, margin=(0, 14, 14, 14)))
        list_box.add(label("最近对话", size=12, color=MUTED, weight="bold",
                           margin=(5, 0, 3, 0)))
        if not sessions:
            list_box.add(label("还没有对话。点击上方按钮开始。", color=MUTED,
                               margin=(12, 0, 0, 0)))
        for session in sessions:
            sid = session["id"]
            card = toga.Box(style=Pack(direction="column", gap=3,
                                       background_color=WHITE, margin_bottom=3))
            title = (session["title"] or "新对话").strip()
            card.add(button("✦  " + title[:46], lambda sid=sid: self.open_session(sid),
                            height=48))
            updated = datetime.fromtimestamp(session["updated_at"]).strftime("%m月%d日 %H:%M")
            card.add(label("更新于 " + updated, size=11, color=MUTED,
                           margin=(0, 12, 9, 12)))
            list_box.add(card)
        content.add(toga.ScrollContainer(content=list_box, horizontal=False,
                                         style=Pack(flex=1)))

    def new_session(self):
        if not self.busy:
            self.open_session(self.store.create_session())

    def rename_session(self, sid: str, title: str) -> None:
        self.store.rename_session(sid, title)
        if sid == self.current_session:
            self.last_status = ""
            self.status_error = False

    def start_from_home(self, prompt_override: str | None = None):
        if self.busy:
            return False
        prompt = (prompt_override if prompt_override is not None else
                  self.home_input.value or "").strip()
        if not prompt:
            self._set_status("请先输入消息")
            return False
        self.open_session(self.store.create_session())
        return self.send(prompt_override=prompt)

    def _stored_display(self, sid: str) -> list[dict]:
        result = []
        tool_names = {}
        for message in self.store.messages(sid):
            role = message["role"]
            if role == "assistant":
                for call in message.get("tool_calls") or []:
                    tool_names[call.get("id")] = call.get("function", {}).get("name", "工具")
            if role in {"user", "assistant", "tool"}:
                text = display_text(message.get("content"))
                if text or role == "tool":
                    result.append({"role": role, "content": text,
                                   "name": tool_names.get(message.get("tool_call_id"), "工具")})
        return result

    def open_session(self, sid):
        if self.busy and sid != self.current_session:
            return
        if sid != self.current_session or not self.busy:
            self.display_messages = self._stored_display(sid)
            self._stream_index = None
        self.current_session = sid
        self.current_view = "chat"
        self._transcript_ready = False
        self._last_full_render = 0.0
        if not self.busy:
            self.last_status = ""
            self.status_error = False
        if self.is_android:
            self.android.ui_show(self._native_chat_state())
            return
        session = next((s for s in self.store.sessions() if s["id"] == sid), None)
        title = (session or {}).get("title", "新对话")
        model = self.store.get_setting("model", "deepseek-flash")
        content = self._screen(title[:28], "模型 · " + model)
        self.transcript_host = content
        self.native_transcript_box = toga.Box(style=Pack(direction="column", gap=10,
                                                         margin=14))
        self.native_transcript = toga.ScrollContainer(
            content=self.native_transcript_box, horizontal=False,
            style=Pack(flex=1))
        content.add(self.native_transcript)
        self._refresh_native_transcript()
        self.transcript = toga.WebView(content=render_page(self.display_messages),
                                       on_webview_load=self._on_transcript_load,
                                       style=Pack(height=1))
        content.add(self.transcript)
        composer = toga.Box(style=Pack(direction="column", height=111,
                                       background_color=WHITE))
        composer.add(toga.Box(style=Pack(height=1, background_color=LINE)))
        inner = toga.Box(style=Pack(direction="column", gap=6, margin=10))
        compose_row = toga.Box(style=Pack(direction="row", gap=8, height=83))
        self.input = toga.MultilineTextInput(placeholder="输入消息，交给 MuseLite 处理…",
                                              style=Pack(flex=1, height=78))
        compose_row.add(self.input)
        self.send_button = button("发送", lambda: self.stop_agent() if self.busy else self.send(),
                                  width=78, height=78)
        compose_row.add(self.send_button)
        inner.add(compose_row)
        composer.add(inner)
        # Place the composer before the growing transcript. Android's native
        # WebView/ScrollView can otherwise push later siblings off the screen.
        self.root.insert(1, composer)
        self._update_busy_controls()
        self._schedule_render()

    def _refresh_native_transcript(self):
        if self.native_transcript_box is None or self.native_transcript is None:
            return
        box = self.native_transcript_box
        scroll = self.native_transcript
        near_bottom = scroll.vertical_position >= scroll.max_vertical_position - 80
        box.clear()
        if not self.display_messages:
            box.add(label("有什么可以帮你？", size=20, weight="bold",
                          margin=(20, 4, 5, 4)))
            box.add(label("输入消息后，对话会显示在这里。", size=13, color=MUTED))
            return
        for message in self.display_messages[-80:]:
            role = message.get("role")
            speaker = {"user": "USER", "assistant": "MUSELITE", "tool": "工具",
                       "error": "错误", "status": "状态"}.get(role, "消息")
            text = str(message.get("content") or "")
            if not text and message.get("pending"):
                text = "正在回复…"
            if not text:
                continue
            card = toga.Box(style=Pack(direction="column", gap=4, margin_bottom=8,
                                       background_color=WHITE))
            card.add(label(speaker, size=11, color=ACCENT, weight="bold",
                           margin=(9, 11, 0, 11)))
            body = label(text[:8000], size=14,
                         color=ERROR if role == "error" else INK,
                         margin=(0, 11, 11, 11))
            if self.is_android and role == "assistant":
                try:
                    from android.text import Html

                    markup = render_markdown(text[:8000])
                    if "<table" not in markup:
                        body._impl.native.setText(Html.fromHtml(
                            markup, Html.FROM_HTML_MODE_COMPACT))
                        body._impl.refresh()
                except Exception:
                    pass
            card.add(body)
            box.add(card)
        if near_bottom:
            self.loop.call_later(0.05, lambda: setattr(
                scroll, "vertical_position", scroll.max_vertical_position))

    def _on_transcript_load(self, widget, **_kwargs):
        if self.current_view == "chat" and widget is self.transcript:
            async def verify_page():
                try:
                    valid = await widget.evaluate_javascript(
                        'document.getElementById("messages") !== null')
                except Exception:
                    return
                if (valid is True and self.current_view == "chat" and
                        widget is self.transcript):
                    self._transcript_ready = True
                    if self.native_transcript is not None:
                        self.transcript_host.remove(self.native_transcript)
                        self.native_transcript = None
                        self.native_transcript_box = None
                    del self.transcript.style.height
                    self.transcript.style.flex = 1
                    self._schedule_render()

            self.loop.create_task(verify_page())

    def _schedule_render(self):
        if self.is_android:
            if self.current_view == "chat" and self._render_handle is None:
                self._render_handle = self.loop.call_later(0.10, self._flush_render)
            return
        if self.current_view == "chat" and self.transcript is not None:
            if self._render_handle is None:
                self._render_handle = self.loop.call_later(0.12, self._flush_render)

    def _flush_render(self):
        self._render_handle = None
        if self.is_android:
            if self.current_view == "chat":
                self.android.ui_chat(self._native_chat_state())
            return
        if self.current_view != "chat" or self.transcript is None:
            return
        self._refresh_native_transcript()
        if not self._transcript_ready:
            now = time.monotonic()
            if now - self._last_full_render < 0.8:
                self._render_handle = self.loop.call_later(
                    0.8 - (now - self._last_full_render), self._flush_render)
                return
            self.transcript.content = render_page(self.display_messages)
            self._last_full_render = now
            return
        markup = render_messages(self.display_messages)
        script = "window.museliteUpdate(" + json.dumps(markup, ensure_ascii=True) + ")"
        try:
            self.transcript.evaluate_javascript(script)
        except Exception:
            self._transcript_ready = False
            self.transcript.content = render_page(self.display_messages)

    def _update_busy_controls(self):
        if self.is_android:
            self.android.ui_busy(self.busy)
            return
        if self.current_view == "chat":
            self.send_button.text = "停止" if self.busy else "发送"
            self.send_button.enabled = True

    def _add_display(self, role: str, text: str, **extras):
        self.display_messages.append({"role": role, "content": text, **extras})
        if self.is_android:
            if self.current_view == "chat" and role in {"user", "error", "status"}:
                self.android.ui_chat(self._native_chat_state())
            else:
                self._schedule_render()
            return
        if role in {"user", "error", "status"}:
            self._refresh_native_transcript()
        self._schedule_render()

    def send(self, prompt_override: str | None = None):
        if self.busy or not self.current_session:
            return False
        if prompt_override is not None:
            prompt = prompt_override
        elif self.is_android:
            prompt = ""
        else:
            prompt = self.input.value or ""
        prompt = prompt.strip()
        if not prompt:
            self._set_status("请先输入消息", error=True)
            return False
        try:
            config = ProviderConfig(
                self.store.get_setting("base_url", "https://api.deepseek.com"),
                self.store.get_setting("model", "deepseek-flash"),
                self.android.load_key(),
                self.store.get_setting("vision", "1") == "1",
            )
            phone = None
            if self.is_android and self.android.phone_status().get("enabled"):
                self.android.phone_start_task()
                self.phone_active = True
                phone = PhoneController(self.android)
            self.active_agent = Agent(self.store, OpenAICompatibleClient(config),
                                      ToolExecutor(self.sandbox, self.browser, phone))
        except Exception as exc:
            if self.phone_active:
                self.android.phone_stop_task()
                self.phone_active = False
            self.active_agent = None
            self._add_display("error", str(exc))
            self._set_status(str(exc), error=True)
            return False
        if not self.is_android:
            self.input.value = ""
        self._add_display("user", prompt)
        self.busy = True
        self._stream_index = None
        self._update_busy_controls()
        self._set_status("MuseLite 正在处理…")
        agent = self.active_agent
        phone_started = self.phone_active
        sid = self.current_session
        loop = self.loop
        finished = threading.Event()
        terminal = [None]

        def agent_event(name, value):
            if name in ("done", "error", "stopped"):
                terminal[0] = (name, value)
            else:
                loop.call_soon_threadsafe(self._event, name, value)

        def watch_notification_stop():
            while not finished.wait(0.2):
                if self.android.phone_stop_requested():
                    agent.stop()
                    return

        def run():
            try:
                agent.run(sid, prompt, agent_event)
            except Exception as exc:
                terminal[0] = ("error", str(exc))
            finally:
                finished.set()
                if phone_started:
                    try:
                        self.android.phone_stop_task()
                    except Exception as exc:
                        if terminal[0] is None:
                            terminal[0] = ("error", str(exc))
                if terminal[0] is not None:
                    loop.call_soon_threadsafe(self._event, *terminal[0])

        if phone_started:
            threading.Thread(target=watch_notification_stop, daemon=True).start()
        threading.Thread(target=run, daemon=True).start()
        return True

    def _event(self, name, value):
        if name == "text":
            if self._stream_index is None:
                self._stream_index = len(self.display_messages)
                self._add_display("assistant", "", pending=True)
            self.display_messages[self._stream_index]["content"] += str(value)
            self._schedule_render()
        elif name == "tool_start":
            self._stream_index = None
            self._add_display("tool", "正在执行…", name=str(value), pending=True)
            self._set_status("正在运行 " + str(value) + "…")
        elif name == "tool_progress":
            for message in reversed(self.display_messages):
                if message["role"] == "tool" and message.get("pending"):
                    message["content"] = browser_progress_text(value)
                    break
            self._schedule_render()
        elif name == "tool_result":
            for message in reversed(self.display_messages):
                if message["role"] == "tool" and message.get("pending"):
                    message["content"] = str(value["result"])
                    message["pending"] = False
                    break
            else:
                self._add_display("tool", str(value["result"]),
                                  name=str(value.get("name", "工具")))
            self._schedule_render()
            self._set_status("工具已完成，MuseLite 正在继续…")
        elif name in ("done", "error", "stopped"):
            self.busy = False
            self.active_agent = None
            self.phone_active = False
            self._stream_index = None
            if self.current_session:
                self.display_messages = self._stored_display(self.current_session)
                users = [m for m in self.store.messages(self.current_session)
                         if m["role"] == "user"]
                if len(users) == 1 and self.current_session not in self._scheduled_session_ids:
                    self.store.rename_session(self.current_session,
                                              str(users[0]["content"])[:32])
            if name == "error":
                self._add_display("error", str(value))
                self._set_status(str(value), error=True)
            elif name == "stopped":
                self._add_display("status", "已停止生成")
                self._set_status("已停止")
            else:
                self._set_status("已完成")
            self._schedule_render()
            if self._pending_scheduled_tasks:
                task_id = self._pending_scheduled_tasks.pop(0)
                self.loop.call_soon(self.trigger_scheduled_task, task_id)
            self._update_busy_controls()

    def stop_agent(self):
        if self.active_agent:
            self._set_status("正在停止…")
            if self.phone_active:
                self.android.phone_stop_task()
            self.active_agent.stop()

    def show_browser(self):
        loop = self.loop

        def run():
            try:
                self.android.call("show_browser", {"visible": True})
                self.android.ui_chat(self._native_chat_state())
            except Exception as exc:
                loop.call_soon_threadsafe(lambda: self._set_status(
                    "浏览器错误：" + str(exc), error=True))

        threading.Thread(target=run, daemon=True).start()

    def _update_browser_preview(self, event: dict) -> None:
        if not self.is_android:
            return
        result = event.get("result") if isinstance(event, dict) else None
        if not isinstance(result, dict):
            return
        # AndroidBridge returns the native response envelope.  Browser calls
        # therefore commonly arrive as {"result": {title, url, text}}.
        # Unwrap it so the compact card shows the readable page content rather
        # than the raw JSON envelope.
        nested = result.get("result")
        if isinstance(nested, dict):
            result = nested
        text = result.get("text", "")
        if not text and isinstance(result.get("items"), list):
            text = " · ".join(str(item.get("text", "")) for item in result["items"][:3]
                              if isinstance(item, dict))
        if not text:
            value = result.get("result", "")
            text = value if isinstance(value, str) else ""
        try:
            self.android.call("set_browser_preview", {
                "title": result.get("title", "网页结果"),
                "url": result.get("url", ""),
                "text": text,
            })
        except Exception:
            pass

    def show_settings(self):
        self.current_view = "settings"
        if self.is_android:
            self.android.ui_show(self._native_settings_state())
            return
        content = self._screen("模型设置", "连接你的 OpenAI 兼容服务")
        fields = toga.Box(style=Pack(direction="column", gap=8, margin=15))
        fields.add(label("连接", size=17, weight="bold", margin=(4, 0, 4, 0)))
        fields.add(label("API 基础 URL", size=12, color=MUTED))
        base = toga.TextInput(value=self.store.get_setting("base_url", "https://api.deepseek.com"),
                              style=Pack(height=42))
        fields.add(base)
        fields.add(label("模型 ID", size=12, color=MUTED, margin=(8, 0, 0, 0)))
        model = toga.TextInput(value=self.store.get_setting("model", "deepseek-flash"),
                               style=Pack(height=42))
        fields.add(model)
        fields.add(label("API Key", size=12, color=MUTED, margin=(8, 0, 0, 0)))
        key = toga.PasswordInput(placeholder="留空则保留现有密钥", style=Pack(height=42))
        fields.add(key)
        fields.add(label("密钥由 Android Keystore 加密保存。", size=11, color=MUTED))
        vision = toga.Switch("模型支持截图图像输入",
                             value=self.store.get_setting("vision", "1") == "1")
        fields.add(vision)
        status = label("", size=12, color=MUTED, margin=(4, 0, 0, 0))

        def save():
            try:
                ProviderConfig(base.value, model.value, "test").endpoint
                if not (model.value or "").strip():
                    raise ValueError("模型 ID 不能为空")
                self.store.set_setting("base_url", base.value.strip().rstrip("/"))
                self.store.set_setting("model", model.value.strip())
                self.store.set_setting("vision", "1" if vision.value else "0")
                if key.value:
                    self.android.save_key(key.value)
                    key.value = ""
                status.text = "✓ 设置已保存"
                status.style.color = ACCENT
                self._set_status("设置已保存")
            except Exception as exc:
                status.text = str(exc)
                status.style.color = ERROR
                self._set_status(str(exc), error=True)

        fields.add(button("保存设置", save, height=48))
        fields.add(status)
        fields.add(toga.Box(style=Pack(height=1, background_color=LINE,
                                       margin=(13, 0, 10, 0))))
        fields.add(label("DeepSeek 示例", size=12, color=MUTED, weight="bold"))
        fields.add(label("https://api.deepseek.com  ·  deepseek-flash",
                         size=12, color=MUTED))
        if self.is_android:
            fields.add(toga.Box(style=Pack(height=1, background_color=LINE,
                                           margin=(13, 0, 10, 0))))
            fields.add(label("手机操作", size=17, weight="bold"))
            state = self.android.phone_status()
            phone_state = label("", size=12, color=MUTED)

            def update_phone_state():
                current = self.android.phone_status()
                phone_state.text = (
                    "系统无障碍：" + ("已启用" if current.get("service") else "未启用") +
                    "  ·  通知：" + ("已允许" if current.get("notifications") else "未允许")
                )
                phone_state.style.color = (ACCENT if current.get("service") and
                                           current.get("notifications") else ERROR)

            def change_phone(widget):
                try:
                    self.android.phone_set_enabled(bool(widget.value))
                    if not widget.value:
                        self.stop_agent()
                    update_phone_state()
                except Exception as exc:
                    self._set_status(str(exc), error=True)

            phone_switch = toga.Switch("允许 Agent 操作手机",
                                       value=bool(state.get("enabled")),
                                       on_change=change_phone)
            fields.add(phone_switch)
            fields.add(label("需在系统设置中手动开启无障碍服务；关闭开关会停止当前任务。",
                             size=11, color=MUTED))
            fields.add(phone_state)
            update_phone_state()
            fields.add(button("打开系统无障碍设置", self.android.phone_open_settings,
                              height=44))
            fields.add(button("申请通知权限", self.android.phone_request_notifications,
                              height=44))
            fields.add(button("刷新授权状态", update_phone_state, height=44))
        content.add(toga.ScrollContainer(content=fields, horizontal=False,
                                         style=Pack(flex=1)))

    def save_native_settings(self, data: dict) -> bool:
        try:
            base = str(data.get("base_url", "")).strip().rstrip("/")
            model = str(data.get("model", "")).strip()
            if not model:
                raise ValueError("模型 ID 不能为空")
            ProviderConfig(base, model, "test").endpoint
            key = str(data.get("key", ""))
            if key:
                self.android.save_key(key)
            self.store.set_setting("base_url", base)
            self.store.set_setting("model", model)
            self.store.set_setting("vision", "1" if data.get("vision") else "0")
            self._set_status("设置已保存")
            return True
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return False

    def set_native_phone_enabled(self, enabled: bool) -> bool:
        try:
            self.android.phone_set_enabled(enabled)
            if not enabled:
                self.stop_agent()
            self.refresh_native_phone_status()
            return True
        except Exception as exc:
            self._set_status(str(exc), error=True)
            return False

    def refresh_native_phone_status(self) -> None:
        try:
            self.android.ui_phone_status(self.android.phone_status())
        except Exception as exc:
            self._set_status(str(exc), error=True)

    def on_exit(self):
        self._cleanup_empty_sessions()
        self.stop_agent()
        return True
