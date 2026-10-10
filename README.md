# MuseLite

MuseLite is a Python-first AI workspace for Android. It combines an OpenAI-compatible chat client, persistent conversations, an execution sandbox, browser tools, scheduled prompts, and optional phone automation in one native Android application.

## Features

- Chat with any OpenAI-compatible HTTPS provider.
- Persistent conversations and model settings stored in SQLite.
- API keys encrypted with the Android Keystore.
- Scheduled prompts: type a prompt, choose a time, and let MuseLite send it in the selected conversation.
- Agent tool loops for multi-step work, with progress and stop controls.
- Reusable Skills with on-demand instructions, scripts, references, and templates; a built-in Skill Creator creates new skills through chat.
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

### Clipboard and chat reply recommendations

For a temporary floating screenshot helper, say **“我需要这个聊天提示的功能，回复语气自然简洁”**
in a MuseLite conversation. The Agent uses `chat_hint` to enable a draggable **帮我回复**
button through the authorized accessibility service. Configure a vision-capable model and
enable image input in Settings first; checking image input does not make a text-only model
support images. Phone Control and the system accessibility service must be enabled.

Switch to your chat app and tap the button. The overlay hides before taking one screenshot,
then the configured model drafts a reply in your requested tone (also applying SOUL.md).
Only a valid reply is copied; failures leave the clipboard unchanged. The screenshot is
sent to your configured model provider, kept temporarily in the private cache, and deleted
after loading. Screenshots are not saved in conversation history; the suggested text is.
No automatic screenshots, clipboard polling, pasting, or sending occur.

Switching apps preserves the button. Returning to MuseLite's conversation list, switching
to another conversation, exiting the app, disabling Phone Control/accessibility, saying
**“关闭聊天提示”**, or tapping **×** closes it. In-flight requests are invalidated so late
results cannot overwrite the clipboard. Screenshots only include the visible screen;
protected pages or unavailable model image input report errors.

`clipboard_read` reads the first text item in Android's clipboard on request, and
`clipboard_write` replaces it with up to 50,000 Unicode characters. Reading requires
MuseLite to be in the foreground on Android 10+; denied reads and non-text clips
return errors. Long reads report `truncated`; they do not imply the entire clip was read.
No clipboard listener runs in the background. Writing can run during a phone task
while the chat app is visible; it copies text without pasting or sending it.

After enabling Phone Control, tell the Agent in the conversation input
“读取我正在聊天的界面，推荐一个回复并复制到剪贴板”, then immediately switch to
the conversation you want help with.
`chat_read` waits up to 30 seconds for an external screen (optionally a specific app),
and reads its visible accessibility text and positions. It excludes password fields
and does not open, tap, scroll or edit the conversation. The Agent checks the screen
is a chat, drafts a reply from the visible context, and copies the reply for you to paste.
Only visible messages are available; hidden history or apps that do not expose text
may require additional context or a screenshot with an image-capable model.

## Use Skills

Open **Settings > Skill** to enable or disable skills and edit their files. Select a skill to edit its complete `SKILL.md`, references, or scripts. Binary templates show file information; **Add text file** creates a supporting resource. Saves validate the YAML `name` and `description`; the name must match the skill directory.

Skill Creator is installed and enabled on first use. Tell the Agent, for example, “Create a skill that turns meeting notes into decisions and action items.” It loads Skill Creator, writes a complete skill directory, and enables the new skill immediately. Enabled skills can be selected automatically by their descriptions or explicitly with `$skill-name`. Disabling Skill Creator removes the creation tool from subsequent requests; it can be enabled again in Settings.

Skills live in `/var/muselite/workspace/skills/<skill-name>/`. Only names and descriptions are initially disclosed to the model; `skill_load` retrieves full instructions and `skill_read` retrieves supporting text as needed. Scripts use the existing Android `shell_execute` sandbox; the desktop preview supports skill management and file access but cannot run Linux scripts.

Each request uses a resource snapshot. User edits and switches apply to the next user message, preserving the workflow of a running task; a skill created by the Agent is added to its current request immediately. The built-in skill is seeded only when absent, so restarting or upgrading preserves user edits and switches. Skills supplement the current request and do not grant additional tools or permissions.

## Local sandbox

### Read and save documents in a phone folder

Open **Settings > 文档保存目录 > 选择手机文件夹**, select a folder in Android's folder picker,
and confirm **Use this folder / Allow**. Choose a subfolder such as `Documents/MuseLite`;
Android may prevent selecting the storage root, Download root, or Android/data.
The folder authorization persists across app restarts and upgrades. The settings show
the actual local path where available; other document providers use a folder name and content URI.
Use **保存测试文档** to verify that a Markdown file appears in the selected folder.

Tell the Agent, for example, “把这份总结保存到手机目录，文件名为 总结.md”.
The `document_directory` tool checks the selected folder and `document_save` saves
UTF-8 text or exports an existing sandbox file (including PDF or other binary files).
Relative subfolders are supported and each file is limited to 25 MB. Existing files
are preserved: duplicate names get a numbered suffix. Files are saved only when requested;
ordinary `file_write` continues to use the app's private workspace.

The Agent can also inspect this same authorized folder, including files created by
other apps. Try “列出我设置目录里的文件” or “读取 报告/总结.md 并总结内容”.
`document_list` lists files and subfolders with names, types, sizes and pagination;
`document_read` reads UTF-8 Markdown, TXT, JSON and other text files up to 1 MiB.
Long text is paginated by Unicode characters (including emoji), and the Agent follows
`next_offset` to read the remaining content. PDF, Word, images, binary data and
non-UTF-8 text are not supported for direct text reading. Reading never creates or
changes files. Access is limited to the selected folder and its subfolders.

If permission is revoked or the folder disappears, select it again in Settings.
**断开保存目录** removes authorization without deleting exported files.

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
