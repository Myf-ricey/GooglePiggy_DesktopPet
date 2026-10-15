# GooglePiggy Desktop Pet

一只会陪你和 Codex 一起工作的 Windows / macOS 透明桌面小猪。

| 平台 | 最新版本 | 下载与说明 |
| --- | --- | --- |
| Windows 10/11 x64 | **0.4.2** | [下载 Windows 便携包](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/download/v0.4.2-windows/GooglePiggy-0.4.2-windows-x64.zip) · [安装与使用](README-WINDOWS.md) |
| macOS 13+ | **0.5.1** | [macOS Release](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/tag/v0.5.1-macos) · [macOS 说明](README-MAC.md) |

## 小猪会做什么

- 思考时拿书阅读，执行工具时追胡萝卜，压缩上下文时整理物品，完成任务时跳跃庆祝。
- 每个独立聊天是一户家庭；子代理显示为最多三只小猪，更多子代理用 `+N` 提示。
- 鼠标移到大猪上展开任务列表，点击切换家庭；每个任务保留自己的动画进度。
- 拖动全家到屏幕外边缘可以藏起，点击露出的尾巴展开。
- 空闲时会偷吃、睡觉；右键菜单可进入休息模式、设置自启动或退出。
- Codex 发出权限请求时显示确认气泡，支持“允许一次”“拒绝”及长内容滚动。

Windows 0.4.2 直接复用 macOS 0.4 的 21 段原始 RGBA 动画；同时修复失效启动记录残留、自动建议会话混入任务列表的问题，并移除权限气泡的“全文”按钮。

## Windows 快速开始

1. 下载上表中的 Windows ZIP，**完整解压**到固定目录。
2. 双击 `pig_pet.exe` 即可试用，无需安装 Python。
3. 如需快捷方式、自启动和 Codex 联动，在解压目录打开 PowerShell，运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

安装器会打印 Codex Hook 审核步骤；按提示在 Codex 的 `/hooks` 中审核十二项 GooglePiggy Hook，再新建聊天或重启客户端。安装目录需要保留，程序和 Hook 都从该目录运行。

升级、可选安装参数、权限说明和故障排查见 [Windows 使用说明](README-WINDOWS.md)。

## macOS

macOS 0.5.1 支持一键下载、签名校验、备份旧版并覆盖重启，保留启动检查、右键检查和发光灯泡提示。Mac 保持独立版本与发行包，安装、首次授权及交互说明见 [README-MAC.md](README-MAC.md)。

## 开发与验证

Windows 源码使用 Python 3.11+，本次在 Python 3.13、Windows 11 x64、150% DPI 单屏环境验证。

```powershell
py -3 -m pip install -r requirements-dev.txt
py -3 tools/test_windows_port.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File hooks/codex-pig-hook.ps1 -SelfTest
py -3 -m PyInstaller --noconfirm pig_pet.spec
py -3 tools/test_windows_runtime.py --exe
```

也可运行 `build-release.ps1` 完成 Windows 构建与检查。macOS 构建见 `build-macos.sh` 和 [Mac 发布检查](RELEASE-CHECKLIST-MAC.md)。

Windows 本版标签为 `v0.4.2-windows`，macOS 保持独立标签。本次使用手动 Windows Actions 构建验证；Release 附件使用经过本机回放及解压验证的版本。

[Windows 0.4.2 发布说明](RELEASE-NOTES-v0.4.2-windows.md) · [Windows 实现与验收](WINDOWS-0.4-HANDOFF.md)

## 许可

程序代码采用 [MIT License](LICENSE)。角色与动画素材的使用范围见 [ASSET-NOTICE.md](ASSET-NOTICE.md)。
