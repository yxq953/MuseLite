"""Build through a local proxy when Java's HTTPS downloads stall on Windows.

Only Google's Android Maven repository and Maven Central are proxied. Downloaded
files are cached beneath the project, and the server lives only for this build.
"""

from __future__ import annotations

import http.server
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


UPSTREAMS = {
    "google": "https://dl.google.com/dl/android/maven2/",
    "central": "https://repo.maven.apache.org/maven2/",
}


def serve_from(cache_root: Path):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self):
            self._handle(send_body=False)

        def do_GET(self):
            self._handle(send_body=True)

        def _handle(self, send_body: bool):
            path = unquote(urlsplit(self.path).path).lstrip("/")
            parts = path.split("/")
            if len(parts) < 2 or parts[0] not in UPSTREAMS or any(
                part in ("", ".", "..") or "\\" in part for part in parts
            ):
                self.send_error(400)
                return
            repository, relative = parts[0], "/".join(parts[1:])
            target = cache_root / repository / relative
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                url = UPSTREAMS[repository] + relative
                try:
                    with urlopen(Request(url, headers={"User-Agent": "MuseLite-build/1.0"}), timeout=90) as response:
                        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                            temporary = Path(output.name)
                            shutil.copyfileobj(response, output)
                    temporary.replace(target)
                    if relative.endswith((".jar", ".aar", ".zip")):
                        print(f"Maven: {repository}/{relative}", flush=True)
                except HTTPError as error:
                    self.send_error(error.code)
                    return
                except Exception as error:
                    temporary = locals().get("temporary")
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                    print(f"Maven download failed: {url}: {error}", file=sys.stderr, flush=True)
                    self.send_error(502)
                    return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()
            if send_body:
                try:
                    with target.open("rb") as source:
                        shutil.copyfileobj(source, self.wfile)
                except ConnectionError:
                    pass

        def log_message(self, _format, *_args):
            pass

    return Handler


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    root_gradle = project / "build/python/android/gradle/build.gradle"
    if not root_gradle.is_file():
        raise SystemExit("Briefcase Android project has not been created")
    cache_root = project / "cache/maven_proxy"
    cache_root.mkdir(parents=True, exist_ok=True)
    class MavenServer(http.server.ThreadingHTTPServer):
        # Gradle resolves many artifacts concurrently. The default backlog of
        # five rejects connections while several upstream requests are active.
        request_queue_size = 256

    server = MavenServer(("127.0.0.1", 0), serve_from(cache_root))
    server.daemon_threads = True
    port = server.server_address[1]
    print(f"Local Maven proxy listening on 127.0.0.1:{port}", flush=True)
    original = root_gradle.read_text(encoding="utf-8")
    original = re.sub(
        r'maven \{ url "http://127\.0\.0\.1:\d+/google"; allowInsecureProtocol = true \}\n'
        r'        maven \{ url "http://127\.0\.0\.1:\d+/central"; allowInsecureProtocol = true \}',
        "google()\n        mavenCentral()",
        original,
    )
    modified = original.replace(
        "google()\n        mavenCentral()",
        f'maven {{ url "http://127.0.0.1:{port}/google"; allowInsecureProtocol = true }}\n'
        f'        maven {{ url "http://127.0.0.1:{port}/central"; allowInsecureProtocol = true }}',
    )
    if modified == original:
        raise SystemExit("Android Maven repositories were not found in build.gradle")
    root_gradle.write_text(modified, encoding="utf-8")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for args in (("build", "android"), ("package", "android", "-p", "debug-apk")):
            print(f"Running Briefcase {' '.join(args)} via local Maven proxy", flush=True)
            result = subprocess.run([sys.executable, "-m", "briefcase", *args], cwd=project, env=os.environ.copy())
            if result.returncode:
                return result.returncode
        return 0
    finally:
        root_gradle.write_text(original, encoding="utf-8")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
