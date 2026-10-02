# OpenMinis Python / Briefcase Android

这是独立的 Python + Briefcase Android 工程，包名为 `com.openminis.python`，面向 Android 11（API 30）及以上的 arm64 设备。聊天、Agent、会话、记忆、工具与沙箱控制由 Python 实现；Android 界面采用原生 Java 控件，Toga 保留桌面预览和 Android 启动入口。Java 还处理 WebView、无障碍服务、前台任务、APK 资源和 Keystore。不会迁移原版应用数据，不含 iOS 功能。

## Windows 构建

需要 Windows x86-64、Python 3.13、联网及约数 GB 空间。**不需要 WSL、Linux 或管理员权限。** 在本工程目录打开 PowerShell 并运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

脚本在 `.venv` 安装 Briefcase 0.4.5/Toga 0.5.6，把 JDK 17 与 Android SDK 下载到 `cache`，并生成 `dist/OpenMinis Python-0.3.1.debug.apk`。首次运行会要求你阅读和接受 Google Android SDK 许可。拒绝许可时无法继续下载 SDK。此工作区的路径较长，因此脚本会校验 SDK 工具下载包，并使用 Windows 扩展路径解压。构建时会临时启动仅监听本机的 Maven 代理，从 Google Maven 和 Maven Central 下载依赖；脚本退出后代理自动关闭。

APK 是 debug 签名包，可直接安装用于测试；它不是商店发布签名包。使用 Android SDK 内的 ADB 安装：

```powershell
$apk = Get-ChildItem .\dist\*.apk | Sort-Object LastWriteTime -Descending | Select-Object -First 1
& .\cache\tools\android_sdk\platform-tools\adb.exe install -r $apk.FullName
```

首次打开后进入“设置”，填写 OpenAI 兼容 HTTPS 基础 URL、模型 ID 与 API Key。DeepSeek 示例：`https://api.deepseek.com`、`deepseek-flash`。首页可直接输入并发送第一条消息，应用会自动创建对话；也可以先点击“开始新对话”。Android 的会话、聊天和设置页使用原生控件，以渐变背景、半透明卡片和明确的状态反馈组成统一视觉风格；消息区独立滚动，输入框固定在底部。助手回答用安全 Markdown 转换后显示基础排版，复杂表格可能按文本显示。API Key 通过 Android Keystore 加密保存在应用私有存储中。会话和模型设置保存在 SQLite 中。

Agent 每条消息最多进行 100 轮工具操作；若仍未完成，会停止调用工具，基于已取得的结果回答并说明未完成部分。后续可在同一会话继续。

## 代理手机操作

在“设置 → 手机操作”中，先打开系统无障碍设置，手动启用 **OpenMinis Python** 服务，再允许通知并开启应用内“允许 Agent 操作手机”开关。此开关默认关闭；关闭时立即停止当前手机操作任务。Android 13 及以上若未授予通知权限，手机操作任务不会启动。部分侧载设备会在系统应用信息中限制无障碍服务开启，需要先解除该设备的限制。

开启后，Agent 可以使用 `phone_use` 读取当前界面、截图、点击或长按、输入或清空、滑动或滚动、按返回/Home/最近任务、按包名打开应用及等待目标出现或消失。使用节点编号时需同时传入 `inspect` 返回的 `generation`；界面变化后应重新读取。截图由模型视觉能力开关控制：启用时仅在当前任务中传给模型，会话数据库不会保存图片；关闭时工具会提示模型改用界面结构。跨应用任务运行时显示常驻通知，可从通知或聊天页停止；进程被系统终止后任务不会自动恢复。

## Android 原生资源

`vendor/native_libs/arm64-v8a` 中的 PRoot 主程序与加载器、`vendor/assets/alpine-minirootfs.tar` 来自 OpenMinis 官方 [Android 1.13 arm64 APK](https://github.com/OpenMinis/OpenMinis/releases/tag/1.13)。源 APK SHA-256 为 `789253f95475fccfcc88a803a0ec8276777b588f5039be773b9774f4bb3f80c6`。对应 PRoot 源码位于仓库 `deps/proot`，项目许可参见仓库根目录 `LICENSE` 与 `THIRD_PARTY_LICENSES.md`。构建脚本会把原生文件复制进 Gradle 工程，并保留 `vendor` 作为可复现输入。

首次运行 `shell_execute` 会解包 Alpine。可以让 Agent 执行 `echo hello; cat /etc/os-release; pwd` 检查沙箱。这个最小镜像没有预装 `python3` 或 `pip`；需要时，在联网状态下执行 `apk add --no-cache python3 py3-pip`。安装结果保留在应用数据中。沙箱会使用 Android 当前网络的 DNS 和 Alpine 自身的命令搜索路径。

## 测试与限制

在仓库根目录运行核心测试：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest -q src/python_briefcase/tests
```

需在 arm64 Android 11+ 设备或模拟器上验证安装、启动、流式对话、多轮工具调用、PRoot 命令、文件/记忆重启后保留、`browser_use` 全部操作，以及 `phone_use` 的跨应用操作和授权撤销。手机操作任务在前台服务运行期间可切换到其他应用。OAuth、语音、系统日历与联系人不在此版范围内。
