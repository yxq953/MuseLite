# OpenMinis Python Android 0.3.1 交接说明

此目录是可独立传递的 Android 项目。包含 Python 应用与 Agent 源码、Java 桥接和界面、Briefcase 模板、Alpine/PRoot 资源、构建脚本、测试、许可证，以及可安装的 arm64 debug APK。包名是 `com.openminis.python`，最低 Android 版本是 11（API 30）。

## 直接安装

在连接了 arm64 Android 设备、并安装了 ADB 的电脑上，从此目录运行：

```powershell
adb install -r '.\dist\OpenMinis Python-0.3.1.debug.apk'
```

运行构建脚本后，也可以使用它下载的 ADB：

```powershell
& .\cache\tools\android_sdk\platform-tools\adb.exe install -r '.\dist\OpenMinis Python-0.3.1.debug.apk'
```

`-r` 保留同包名旧版应用的数据。首次进入设置后填写兼容 OpenAI Chat Completions 的基础 URL、模型 ID 和 API Key。此交接包不含用户数据或 API Key。

## 从源码构建 APK（Windows）

需要 Windows x64、Python 3.13、网络、足够磁盘空间，以及接受 Android SDK 许可。不需要 WSL。进入此目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

脚本按需在此目录生成 `.venv`、`cache`、`build` 和 `dist`，下载 JDK/Android SDK/Gradle，使用本目录的 `template`、`vendor`、`java`、`res` 和 `src` 重建并检查 APK。构建产物位于 `dist`。本目录附带的 APK 已由此流程构建。

## 测试

在此目录运行：

```powershell
python -m pip install 'toga==0.5.6' 'markdown-it-py==4.2.0' pytest
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest -q tests
```

实机安装后，可让 Agent 执行 `echo hello; cat /etc/os-release; pwd` 检查 Linux 沙箱。Alpine 最小镜像未预装 Python 或 pip；如需在沙箱内使用，请联网执行 `apk add --no-cache python3 py3-pip`。手机操作另需用户在 Android 设置中启用无障碍服务，并打开应用内开关。

## 交接范围

`src/python_briefcase` 是唯一的应用工程；本目录已复制其构建输入及最新 APK，并附上根目录的 `LICENSE` 和 `THIRD_PARTY_LICENSES.md`。未包含本机虚拟环境、SDK/Gradle/Maven 缓存、历史 APK、构建中间文件、日志或用户预览数据。这些文件与原电脑绑定或可由脚本重新生成。

Windows 单元测试和 APK 构建已通过，结果记录在 `BUILD_VERIFIED.md`。交接时没有连接 Android 设备，因此 PRoot、WebView 和跨应用无障碍操作还需要接收方在设备上验收。
