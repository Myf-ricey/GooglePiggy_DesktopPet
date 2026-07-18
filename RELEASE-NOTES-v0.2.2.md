# GooglePiggy Desktop Pet v0.2.2

本版本在原有 Windows 桌宠基础上加入原生 macOS 版本，并保留相同的动画、Codex
状态联动和权限交互。

## 新增：原生 macOS 版

- 原生 Swift/AppKit 透明置顶窗口，不依赖 Python、PowerShell 或 Homebrew。
- 同时支持 Apple Silicon 与 Intel；提供 Universal 2 ZIP 和 DMG。
- 呼吸待机、点击躺平、拖动左拱、思考追胡萝卜、完成跳跃与庆祝特效。
- Codex `PermissionRequest` 疑问猪气泡，可直接回传“允许/拒绝”。
- LaunchAgent 开机自启动、单实例、跨桌面空间显示。
- 原生安装器、卸载器、构建脚本和 GitHub Actions 工作流。

## macOS 测试周期修复

- 修复取消右键菜单后透明面板可能消失、需要重新启动的问题。
- 补充 Codex 用户 Hook 的首次信任流程；安装后会明确提示进入 `/hooks` 审核。
- 修复权限说明被错误限制为单行、后半段过早显示省略号的问题。
- 加入对应的窗口生命周期、安装提示和长权限文案回归检查。

## Windows

Windows 10/11 x64 版本、安装器、PowerShell Hook、PyInstaller 构建流程和发布工作流
继续保留。跨平台状态桥只增加 macOS 状态目录支持，不改变 Windows 的
`%LOCALAPPDATA%\GifPigDesktopPet\` 路径。

## macOS 首次安装提醒

1. 运行发布包中的 `install.command`。
2. 在终端运行 `codex`，输入 `/hooks`。
3. 核对 GooglePiggy Hook 的安装路径并完成信任。
4. 完全退出并重新打开 Codex 桌面版。

本地 Mac 包使用 ad-hoc 签名。若 macOS 首次拦截，请按住 Control 点击应用或安装
脚本，选择“打开”。面向普通用户发布时，建议使用 Developer ID 签名并完成 Apple
公证。

## 建议上传的 Release Assets

```text
GifPigDesktopPet-windows-x64.zip
GooglePiggy-macos-universal.zip
GooglePiggy-macos-universal.dmg
GooglePiggy-macos-arm64.zip
GooglePiggy-macos-arm64.dmg
GooglePiggy-macos-x64.zip
GooglePiggy-macos-x64.dmg
```
