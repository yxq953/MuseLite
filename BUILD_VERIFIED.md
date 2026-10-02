# 本机构建验证

验证日期：2026-09-30；平台：Windows x64、Python 3.13。

- 在此交接目录运行 `build_windows.ps1`，Briefcase 和 Gradle 构建成功。
- 运行 `python -m pytest -q tests`：23 项通过。
- `scripts/verify_apk.py` 检查通过，APK 包含 Alpine 镜像与 arm64 PRoot 原生组件。
- APK：`dist/OpenMinis Python-0.3.1.debug.apk`；包名 `com.openminis.python`；版本 `0.3.1`；最低 API 30；arm64；Android v2 签名校验通过。
- APK SHA-256：`1dcf6db2056940e0f173d57c70166eae4666129f904d9660c5d1d2c4403e41df`。

本机下载 Android 命令行工具时连接停滞，因此构建使用了本机已下载且已校验的 Android SDK、JDK、Gradle 和 Maven 缓存；交接包不含这些机器专属缓存。接收方重新构建需要网络。验证时没有连接 Android 设备，也没有配置模拟器，因此尚未完成安装启动及 PRoot/WebView/无障碍功能的设备验收。
