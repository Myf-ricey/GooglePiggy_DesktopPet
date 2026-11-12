# Windows 0.5.10 · 任务较多时更流畅

- 减少桌宠运行时反复扫描旧任务记录带来的动画卡顿和响应延迟。
- 有新任务记录时优先读取变化的文件。启动时恢复历史，读取失败会重试，通知丢失时会完整补查。

## 下载与升级

已安装版可以右键猪猪，选「检查更新…」。首次安装请下载 `GooglePiggy-0.5.10-windows-x64.zip`，完整解压到固定目录。双击 `pig_pet.exe` 可以试用，运行包内 `install.ps1` 可安装桌面入口和 Codex 联动。升级会保留外观设置与任务记录。

## 验证

在 Windows 11 单屏、150% DPI 上，用 12,321 条合成记录对照测试。猪猪恢复任务后，较慢的窗口响应从约 217 毫秒降到 51 毫秒，画面变化间隔从约 273 毫秒降到 83 毫秒，两项均为 p95。首次恢复大量历史仍需约 8 秒。

构建号 `20261112.1-event-discovery-release`。[验收记录](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/download/v0.5.10-windows/ACCEPTANCE.md) · [下载校验值](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/download/v0.5.10-windows/SHA256SUMS.txt)
