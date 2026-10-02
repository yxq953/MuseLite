# MuseLite

MuseLite is a Python-first AI workspace for Android. It combines an OpenAI-compatible chat client, persistent conversations, an execution sandbox, browser tools, scheduled prompts, and optional phone automation in one native Android application.

## About

MuseLite is built around three ideas:

- **Muse** is the creative layer: it helps turn rough intent into useful questions, plans, and drafts.
- **Dots** are the small signals of activity and state that keep a workspace easy to scan: sessions, scheduled work, tool progress, and status updates stay visible without getting in the way.
- **Agent** is the action layer: it can call tools, work through multi-step tasks, use the local sandbox, browse pages, and operate an Android device when the user explicitly enables that capability.

The project is designed for personal, inspectable workflows. Conversations and settings stay on the device unless a configured model provider receives a request. The Android application uses native Java UI and services where platform access matters, while Python owns the chat, Agent, storage, and tool orchestration layers.

## Features

- Chat with any OpenAI-compatible HTTPS provider.
- Persistent conversations and model settings stored in SQLite.
- API keys encrypted with the Android Keystore.
- Scheduled prompts: type a prompt, choose a time, and let MuseLite send it in the selected conversation.
- Agent tool loops for multi-step work, with progress and stop controls.
- A persistent Alpine Linux sandbox powered by PRoot for shell commands and workspace files.
- Browser tools for fetching pages, managing tabs, and saving useful results into the workspace.
- Optional Android phone control through the accessibility service and a foreground task service.
- Safe Markdown rendering for assistant messages.
- Android 11+ arm64 support, with a desktop Toga preview for development.

## Requirements

- Windows x86-64 for the provided build script.
- Python 3.13.
- Internet access on the first build to download Briefcase, the Android SDK, Gradle, and Maven dependencies.
- An Android 11+ arm64 device or emulator for the packaged application.

WSL, Linux, and administrator privileges are not required by `build_windows.ps1`.

## Build the APK on Windows

From the repository root, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

The script creates a local `.venv`, downloads build tools into `cache`, stages the Android project, and writes a debug APK to `dist`. On the first run, accept the Android SDK licenses when prompted.

Install the newest APK on a connected device with:

```powershell
$apk = Get-ChildItem .\dist\*.apk |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
& .\cache\tools\android_sdk\platform-tools\adb.exe install -r $apk.FullName
```

Debug APKs are intended for development and testing. They are not release-signed packages for an app store.

## Configure a model

Open **Settings** after launching MuseLite and enter:

1. An OpenAI-compatible HTTPS base URL.
2. A model ID.
3. An API key.

For example, DeepSeek can use `https://api.deepseek.com` with the model ID `deepseek-flash`. The provider endpoint is validated before settings are saved. The API key is kept in the app's private storage and encrypted with Android Keystore.

## Schedule a prompt

1. Tap **Start New Conversation**.
2. Type the prompt you want MuseLite to send later.
3. Tap **Schedule** beside the input field.
4. Choose the hour and minute, then tap **Confirm**.

MuseLite returns to the main screen after confirmation. At the selected time, Android opens the saved conversation and sends the prompt that was in the input field when the task was created. An empty draft is not saved as a recent conversation.

## Use Agent phone control

Phone control is disabled by default. To enable it:

1. Open **Settings > Phone Control**.
2. Enable the MuseLite accessibility service in Android system settings.
3. Grant notification permission when Android requests it.
4. Turn on **Allow Agent to operate the phone** in MuseLite.

When enabled, the Agent can inspect the current screen, tap or long-press, type or clear text, swipe, press Back/Home/Recents, open an app by package name, and wait for a target to appear or disappear. Tasks run in a foreground service with a persistent notification and can be stopped from the notification or the chat. The Agent does not regain access after the process is killed.

## Local sandbox

The first `shell_execute` call unpacks the bundled Alpine root filesystem. The persistent paths are:

- `/var/muselite/workspace` for user files.
- `/var/muselite/memory` for saved notes and memory.

The minimal image does not include Python or pip. If needed and network access is available, install them inside the sandbox with:

```sh
apk add --no-cache python3 py3-pip
```

The installed packages and files remain in the app's private data directory.

## Project layout

```text
src/muselite_py/          Python UI, Agent, storage, tools, and sandbox
java/com/muselite/python/ Android bridges, services, scheduling, and phone control
template/                 Briefcase Android template and native resources
scripts/                  Windows build, staging, verification, and asset tools
vendor/                   Reproducible Alpine and PRoot inputs
tests/                    Python unit tests
```

## Development checks

Run the Python test suite from the repository root:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest -q tests
```

For Android validation, install the generated APK on an Android 11+ arm64 device and verify launch, streaming chat, scheduled prompts, multi-step tool calls, sandbox commands, persistence after restart, browser tools, and phone-control authorization changes.

## Native components and licenses

The bundled PRoot loader, PRoot binary, and Alpine root filesystem under `vendor/` are derived from the OpenMinis Android 1.13 release. See `LICENSE` and `THIRD_PARTY_LICENSES.md` for project and third-party license information.

MuseLite is released under the GNU General Public License v3.0. See `LICENSE` for the full text.
