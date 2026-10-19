# GooglePiggy Desktop Pet

一只会陪你和 Codex 一起工作的 Windows / macOS 透明桌面小猪。

| 平台 | 最新版本 | 下载与说明 |
| --- | --- | --- |
| Windows 10/11 x64 | **0.5.3** | [下载 Windows 便携包](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/download/v0.5.3-windows/GooglePiggy-0.5.3-windows-x64.zip) · [安装与使用](README-WINDOWS.md) |
| macOS 13+ | **0.5.3** | [macOS Release](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/tag/v0.5.3-macos) · [macOS 说明](README-MAC.md) |

## 小猪会做什么

- 思考时拿书阅读，执行工具时追胡萝卜，压缩上下文时整理物品，完成任务时跳跃庆祝。
- 每个独立聊天是一户家庭；子代理显示为最多三只小猪，更多子代理用 `+N` 提示。
- 鼠标移到大猪上展开任务列表，点击切换家庭；每个任务保留自己的动画进度。
- 拖动全家到屏幕外边缘可以藏起，点击露出的尾巴展开。
- 空闲时会偷吃、睡觉；右键菜单可进入休息模式、设置自启动或退出。
- Codex 发出权限请求时显示确认气泡，支持“允许一次”“拒绝”及长内容滚动。

Windows 0.5.3 保留原始 RGBA 动画与多任务家庭，加入启动／手动检查更新、灯泡提示、下载进度与可回滚的原路径更新；扩展后台内部会话过滤，并修复压缩日志和旧任务元数据遗漏导致的小猪持续运行。

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

macOS 0.5.3 修复运行中强制隐藏后提前弹出，并补充建议安全检查后台会话过滤，并支持一键下载、签名校验、备份旧版并覆盖重启，保留启动检查、右键检查和发光灯泡提示。Mac 保持独立版本与发行包，安装、首次授权及交互说明见 [README-MAC.md](README-MAC.md)。

## 版本规划

同一轮功能更新使用同一目标版本号，允许 Windows / macOS 错峰发布；平台专属修复允许补丁号暂时不同。Windows 本轮已完成 **0.5.3** 的移植与验收。详见 [版本号规则](VERSIONING.md) 和 [Windows 交接](releases/macos-0.5.3/WINDOWS-HANDOFF.md)。

## 开发与验证

Windows 源码使用 Python 3.11+，本次在 Python 3.13、Windows 11 x64、150% DPI 单屏环境验证。

```powershell
py -3 -m pip install -r requirements-dev.txt
py -3 -m unittest tools.test_handoff_053 tools.test_windows_port tools.test_windows_update tools.test_internal_memory tools.test_compressed_rollout tools.test_state_audit -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File hooks/codex-pig-hook.ps1 -SelfTest
py -3 -m PyInstaller --noconfirm pig_pet.spec
py -3 tools/test_windows_runtime.py --exe
py -3 tools/test_state_runtime.py dist/GifPigDesktopPet/pig_pet.exe
```

也可运行 `build-release.ps1` 完成 Windows 构建与检查。macOS 构建见 `build-macos.sh` 和 [Mac 发布检查](RELEASE-CHECKLIST-MAC.md)。

Windows 本版标签为 `v0.5.3-windows`，构建 `20261019.1-hidden-family`，macOS 保持独立标签。Windows 已通过 56 项回归、12 项原生回放、5 项四边隐藏验收、7 项隔离观察器验收和 5 项升级／回滚验收；发行附件使用经本机验证的便携程序。

[Windows 0.5.3 发布说明](RELEASE-NOTES-v0.5.3-windows.md) · [验收报告](releases/windows-0.5.3/ACCEPTANCE.md)

## 许可

程序代码采用 [MIT License](LICENSE)。角色与动画素材的使用范围见 [ASSET-NOTICE.md](ASSET-NOTICE.md)。

## Windows 0.5.3

运行中隐藏绑定家庭，等待主任务和子任务结束后完整庆祝；新增建议安全检查过滤；首次运行默认登录自启动，并保留手动关闭的选择。[发布说明](RELEASE-NOTES-v0.5.3-windows.md) · [验收](releases/windows-0.5.3/ACCEPTANCE.md)。
