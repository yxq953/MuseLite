"""Alpine/PRoot runner. Only the Android packaged binary may execute guest code."""

from __future__ import annotations

import os
import posixpath
import shutil
import subprocess
import tarfile
import threading
import time
from pathlib import Path
from typing import Callable


class SandboxError(RuntimeError):
    pass


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _validate_rootfs_members(members: list[tarfile.TarInfo]) -> None:
    names: set[str] = set()
    links: set[str] = set()
    files: set[str] = set()
    for member in members:
        name = member.name
        if (not name or name.startswith("/") or "\\" in name
                or ".." in name.split("/")):
            raise SandboxError("Alpine 镜像包含越界路径")
        normalized = posixpath.normpath(name)
        if normalized in names:
            raise SandboxError("Alpine 镜像包含重复路径")
        names.add(normalized)
        if member.isfile():
            files.add(normalized)
        elif member.issym() or member.islnk():
            links.add(normalized)
            link = member.linkname
            if not link or "\\" in link:
                raise SandboxError("Alpine 镜像包含无效链接")
            if member.issym():
                # An absolute symlink is rooted inside the PRoot guest.
                source = (link.lstrip("/") if link.startswith("/") else
                          posixpath.join(posixpath.dirname(normalized), link))
            else:
                # Tar hardlink names are relative to the archive root.
                source = link.lstrip("/")
            link_target = posixpath.normpath(source)
            if link_target == ".." or link_target.startswith("../"):
                raise SandboxError("Alpine 镜像包含越界链接")
        elif not member.isdir():
            raise SandboxError("Alpine 镜像包含不支持的文件类型")
    for member in members:
        normalized = posixpath.normpath(member.name)
        if any(parent in links for parent in _parent_paths(normalized)):
            raise SandboxError("Alpine 镜像包含穿过符号链接的路径")
        if member.islnk() and posixpath.normpath(member.linkname.lstrip("/")) not in files:
            raise SandboxError("Alpine 镜像包含无效硬链接")


def install_rootfs(archive: Path, root: Path) -> None:
    marker = root / ".muselite-rootfs-ready"
    if marker.is_file():
        return
    if not archive.is_file():
        raise SandboxError(f"缺少 Alpine 镜像：{archive}")
    staging = root.with_name(root.name + ".installing")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        with tarfile.open(archive, "r:*") as tar:
            members = tar.getmembers()
            _validate_rootfs_members(members)

            # Create links last so no archive member can write through a link
            # into a different host directory during extraction.
            for member in members:
                if member.issym() or member.islnk():
                    continue
                relative = Path(posixpath.normpath(member.name))
                target = staging / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    stream = tar.extractfile(member)
                    if stream is None:
                        raise SandboxError("无法读取 Alpine 镜像文件")
                    with stream, target.open("wb") as output:
                        shutil.copyfileobj(stream, output)
                    target.chmod(member.mode & 0o777)
            for member in members:
                target = staging / posixpath.normpath(member.name)
                if member.islnk():
                    source = staging / posixpath.normpath(member.linkname.lstrip("/"))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.link(source, target)
                elif member.issym():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(member.linkname)
        (staging / "root").mkdir(exist_ok=True)
        (staging / "var/muselite/workspace").mkdir(parents=True, exist_ok=True)
        marker_staging = staging / marker.name
        marker_staging.write_text("ready\n", encoding="utf-8")
        if root.exists():
            shutil.rmtree(root)
        staging.rename(root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _parent_paths(name: str):
    parent = posixpath.dirname(name)
    while parent not in ("", "."):
        yield parent
        parent = posixpath.dirname(parent)


class ProotSandbox:
    def __init__(self, app_dir: Path, assets_dir: Path, native_lib_dir: Path,
                 dns_config: Callable[[], str] | None = None):
        self.app_dir = Path(app_dir)
        self.assets_dir = Path(assets_dir)
        self.native_lib_dir = Path(native_lib_dir)
        self.dns_config = dns_config
        self.root = self.app_dir / "alpine"
        self.workspace = self.app_dir / "workspace"
        self.memory = self.app_dir / "memory"
        self._process: subprocess.Popen[str] | None = None
        self._process_lock = threading.Lock()

    def prepare(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.memory.mkdir(parents=True, exist_ok=True)
        install_rootfs(self.assets_dir / "alpine-minirootfs.tar", self.root)
        if self.dns_config is not None:
            config = self.dns_config()
            if config:
                resolv_conf = self.root / "etc/resolv.conf"
                resolv_conf.write_text(config, encoding="utf-8")
        for name in ("libproot.so", "libproot-loader.so", "libproot-loader32.so"):
            path = self.native_lib_dir / name
            if not path.is_file():
                raise SandboxError(f"APK 缺少原生组件：{name}")
        if not os.access(self.native_lib_dir / "libproot.so", os.X_OK):
            raise SandboxError("PRoot 不可执行；请检查 APK 原生库解包设置")

    def resolve(self, guest_path: str, *, must_exist: bool = False) -> Path:
        if not guest_path.startswith("/"):
            raise SandboxError("文件路径须为沙箱绝对路径")
        mapped = None
        for prefix, base in (
            ("/var/muselite/workspace", self.workspace),
            ("/var/muselite/memory", self.memory),
        ):
            if guest_path == prefix or guest_path.startswith(prefix + "/"):
                mapped = base / guest_path[len(prefix):].lstrip("/")
                root = base
                break
        if mapped is None:
            mapped = self.root / guest_path.lstrip("/")
            root = self.root
        resolved = mapped.resolve()
        if not _inside(root.resolve(), resolved):
            raise SandboxError("文件路径超出沙箱")
        if must_exist and not resolved.exists():
            raise SandboxError(f"文件不存在：{guest_path}")
        return resolved

    def execute(
        self, command: str, timeout: int = 900,
        cancel: threading.Event | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        self.prepare()
        if not command.strip():
            raise SandboxError("命令不能为空")
        timeout = max(1, min(int(timeout), 3600))
        tmp = self.app_dir / "proot-tmp"
        tmp.mkdir(exist_ok=True)
        args = [str(self.native_lib_dir / "libproot.so"), "-0", "--link2symlink",
                "-r", str(self.root), "-b", "/dev", "-b", "/proc", "-b", "/sys",
                "-b", f"{self.workspace}:/var/muselite/workspace",
                "-b", f"{self.memory}:/var/muselite/memory",
                "-w", "/root", "/bin/sh", "-c", command]
        env = os.environ.copy()
        env.update({"PROOT_TMP_DIR": str(tmp),
                    "PROOT_LOADER": str(self.native_lib_dir / "libproot-loader.so"),
                    "PROOT_LOADER_32": str(self.native_lib_dir / "libproot-loader32.so"),
                    "LD_LIBRARY_PATH": str(self.native_lib_dir),
                    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    "HOME": "/root"})
        started = time.monotonic()
        result = self._run_once(args, env, started, timeout, cancel, on_output)
        if (result["exit_code"] in (132, 135, 139, 159)
                and not result["output"] and result["duration_ms"] < 1500
                and not (cancel and cancel.is_set())):
            retry_env = {**env, "PROOT_NO_SECCOMP": "1"}
            result = self._run_once(args, retry_env, started, timeout, cancel, on_output)
            result["seccomp_retry"] = True
        return result

    def _run_once(self, args: list[str], env: dict[str, str], started: float,
                  timeout: int, cancel: threading.Event | None,
                  on_output: Callable[[str], None] | None) -> dict[str, object]:
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True,
                                       encoding="utf-8", errors="replace", env=env)
        except OSError as exc:
            raise SandboxError(f"无法启动 PRoot：{exc}") from exc
        with self._process_lock:
            self._process = process
        output: list[str] = []
        output_size = 0
        try:
            # The reader thread prevents a silent process from blocking timeout checks.
            def read_output() -> None:
                nonlocal output_size
                assert process.stdout is not None
                for line in process.stdout:
                    if output_size < 1_000_000:
                        piece = line[:1_000_000 - output_size]
                        output.append(piece)
                        output_size += len(piece)
                        if on_output:
                            on_output(piece)

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            while process.poll() is None:
                if cancel is not None and cancel.is_set():
                    process.kill()
                    raise InterruptedError("命令已取消")
                if time.monotonic() - started >= timeout:
                    process.kill()
                    raise SandboxError(f"命令超时（{timeout} 秒）")
                time.sleep(0.1)
            reader.join(timeout=2)
            result = {"output": "".join(output), "exit_code": process.returncode,
                      "duration_ms": round((time.monotonic() - started) * 1000)}
            if output_size >= 1_000_000:
                result["truncated"] = True
            if process.returncode in (-31, -11) and not output:
                result["hint"] = "PRoot 可能受到设备 seccomp 限制"
            return result
        finally:
            with self._process_lock:
                self._process = None
            if process.poll() is None:
                process.kill()
            process.wait()

    def stop(self) -> None:
        with self._process_lock:
            if self._process is not None:
                self._process.kill()
