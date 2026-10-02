"""Desktop preview support without Android APIs or plaintext key storage."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .sandbox import ProotSandbox, SandboxError


class DesktopBridge:
    def __init__(self, files_dir: Path | None = None):
        local = os.environ.get("LOCALAPPDATA")
        self.files_dir = Path(files_dir) if files_dir else (
            Path(local) / "MuseLitePython" if local else Path.home() / ".muselite-python"
        )
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self._key = ""

    def save_key(self, value: str) -> None:
        # A desktop preview has no Android Keystore. Keep credentials in memory.
        self._key = value

    def load_key(self) -> str:
        return self._key

    def call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Android WebView 仅在 Android 应用中可用")


class DesktopSandbox(ProotSandbox):
    available = False

    def __init__(self, app_dir: Path):
        super().__init__(app_dir, app_dir / "assets", app_dir / "native_libs")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.memory.mkdir(parents=True, exist_ok=True)

    def prepare(self) -> None:
        raise SandboxError("Linux PRoot 沙箱仅在 Android 应用中可用")

    def execute(self, command: str, timeout: int = 900, cancel=None,
                on_output=None) -> dict[str, object]:
        raise SandboxError("Linux PRoot 沙箱仅在 Android 应用中可用")

    def resolve(self, guest_path: str, *, must_exist: bool = False) -> Path:
        if not (guest_path == "/var/muselite/workspace"
                or guest_path.startswith("/var/muselite/workspace/")
                or guest_path == "/var/muselite/memory"
                or guest_path.startswith("/var/muselite/memory/")):
            raise SandboxError("桌面预览只能读写 /var/muselite/workspace 和 /var/muselite/memory")
        return super().resolve(guest_path, must_exist=must_exist)
