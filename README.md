# GooglePiggy Desktop Pet

一只会陪你和 Codex、Claude Code 一起工作的 Windows / macOS 桌面小猪。它会根据
CLI 的状态切换动作，也能在你暂时不需要它时悄悄躲进屏幕边缘。

它不是简单贴在屏幕上的静态图片，而是一个透明置顶的小桌宠：平时轻轻呼吸，拖动时会左拱，点一下会躺平；当 Codex 或 Claude Code 正在工作时，它会追胡萝卜；任务完成时，它会跳起来庆祝，还会撒一点亮晶晶和小烟花。遇到权限请求时，它会变成疑问猪，在头顶弹出允许/拒绝气泡，并把选择传回对应的 CLI。Claude Code 的联动目前仅支持 Windows。

这个项目最早只是一个“我想让工作状态变得更可爱一点”的小点子。现在它已经被
整理成可以直接安装、自由修改，并能继续扩展到不同桌面平台的开源小工具。

> **当前版本：`v0.3.2`。** Windows 和 macOS 现在都支持完整的空闲触边隐藏、尾巴
> 进出动画和点尾跳回；两端使用一致的边缘交互规则。

## Features

- Idle: 循环播放很轻微的呼吸动画。
- Left click: 没有其他动作时，播放一次躺平动画。
- Dragging: 拖动猪猪时播放左拱动画。
- Edge hiding (Windows / macOS): 空闲时拖到屏幕外边缘，猪猪会用平滑的短暂进出动画
  收进屏幕，只露出可点击的小尾巴；点一下尾巴就会沿同样的节奏滑回。Windows 和
  macOS 都只对物理外边缘生效，内部显示器接缝不会误触发；工作、权限请求和完成状态
  会自动保持或恢复可见。
- CLI thinking: Codex 或 Claude Code 工作或思考时，播放追胡萝卜动画。
- CLI success: Codex 或 Claude Code 完成回答时，播放跳跳猪庆祝动画，并显示小火花和烟花。
- CLI permission: Codex 或 Claude Code 请求权限时，播放疑问猪，并显示允许/拒绝气泡（Claude Code 目前仅支持 Windows）。
- Right-click menu: 支持动作预览、开机自启动开关、退出。
- Portable build: Windows 便携版不要求用户安装 Python。
- Native Mac build: macOS 版是原生透明 AppKit 应用，运行时同样不要求 Python。
- Open-source ready: 源码、素材、构建脚本、GitHub Actions workflow 都在仓库里。

## Compatibility

| Item | Status |
| --- | --- |
| Windows 10/11 x64 | Supported (`v0.3.2`, including tail edge hiding) |
| macOS 13+ Apple Silicon | Supported (`v0.3.2`, including tail edge hiding) |
| macOS 13+ Intel | Supported (`v0.3.2`, including tail edge hiding) |
| Portable ZIP | Supported |
| macOS DMG | Supported |
| Python source run | Python 3.11+, tested with Python 3.13 |
| Codex hooks | Optional |
| Claude Code hooks | Optional (Windows only for now) |
| Linux | Not supported yet |

Windows 使用 layered-window APIs；macOS 使用原生 AppKit 透明浮动面板。两套运行时
共享同一套动画清理、归一和锚点规则。

Runtime state is stored under:

```text
%LOCALAPPDATA%\GifPigDesktopPet\
```

The main status file is:

```text
%LOCALAPPDATA%\GifPigDesktopPet\codex-status.json
```

macOS runtime state is stored under:

```text
~/Library/Application Support/GifPigDesktopPet/
```

## Quick Start For Users

### macOS

#### 1. 下载

优先从 GitHub Releases 下载通用包，它同时支持 Apple Silicon 与 Intel：

```text
GooglePiggy-macos-universal-v0.3.2.zip # Apple Silicon + Intel
GooglePiggy-macos-universal.dmg
```

仓库中也提供了已验证的完整 Mac 便携包：

[GooglePiggy-macos-universal-v0.3.2.zip](releases/GooglePiggy-macos-universal-v0.3.2.zip)

GitHub Actions 也会生成较小的单架构包：

```text
GooglePiggy-macos-arm64.zip # Apple Silicon（M 系列）
GooglePiggy-macos-x64.zip   # Intel
```

#### 2. 安装并启动

1. 解压 ZIP，或打开 DMG。
2. 双击发布文件夹里的 `install.command`。
3. 安装器会把应用复制到 `~/Applications/GooglePiggy.app`，安装 Codex
   hooks，启用当前用户开机自启动，然后启动猪猪。
4. 如果 macOS 拦截未公证应用，请按住 Control 点击 `install.command`，选择
   “打开”，再确认一次。

只想临时体验动画时，也可以直接双击 `GooglePiggy.app`，但这样不会自动安装
Codex hooks 和开机自启动。

#### 3. 完成 Codex Hook 首次授权

Codex 不会自动运行新写入的用户 Hook。首次安装后必须完成一次安全确认：

1. 打开“终端”，运行 `codex`。
2. 输入 `/hooks`。
3. 核对命令指向
   `~/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy --hook`。
4. 选择 `Trust all and continue`；如果列表里还有其他来源不明的 Hook，只信任
   GooglePiggy 对应项。
5. 退出终端版 Codex，完全退出并重新打开 Codex 桌面版。

只重启 Codex、没有完成 `/hooks` 信任确认时，待机和鼠标动画正常，但思考、完成
与权限互动不会触发。

#### 4. 验证与日常操作

- 给 Codex 发送一条新任务：思考时猪猪追胡萝卜，完成时跳跃庆祝。
- 单击猪猪：播放一次躺平动画。
- 按住并拖动：播放左拱动画并移动猪猪。
- 空闲时拖到任一屏幕外边缘：猪猪会跳进屏幕，只留下尾巴；单击尾巴即可跳回。
- 右键猪猪：切换联动模式、预览动作、开关自启动或退出。
- Codex 请求权限：气泡会完整换行显示摘要，可在猪猪上点击“允许”或“拒绝”。

安装器可选参数：

```zsh
./install.command --no-autostart
./install.command --no-codex-hooks
./install.command --no-start
```

完整 Mac 说明见 [README-MAC.md](README-MAC.md)，移植审计见
[MACOS-PORTING.md](MACOS-PORTING.md)，上传前检查见
[RELEASE-CHECKLIST-MAC.md](RELEASE-CHECKLIST-MAC.md)。

### Windows

已核验的 Windows 便携包可直接从仓库下载：

[GifPigDesktopPet-windows-x64.zip](releases/GifPigDesktopPet-windows-x64.zip)

也可以从 GitHub Releases 下载 Windows release ZIP：

```text
GifPigDesktopPet-windows-x64.zip
```

Unzip it, then run in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer will:

- create a desktop shortcut;
- optionally enable current-user autostart;
- install the Codex hook into `~\.codex\hooks.json`;
- install the Claude Code hook into `~\.claude\settings.json`;
- start the desktop pet.

If you only want the pet and do not want Codex integration:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoCodexHooks
```

If you only want the pet and do not want Claude Code integration:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoClaudeHooks
```

Claude Code picks up hook changes on its next restart, so restart any running
`claude` session after installing.

If you only want to run it temporarily:

```powershell
.\start-pig-pet.cmd
```

To uninstall the current-user shortcut, autostart entry, and hooks added by this project:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

The uninstall script does not delete the extracted program folder itself.

#### Windows 边缘隐藏

Windows 端在猪猪处于 `responsive` 空闲模式时支持边缘隐藏：

- 把猪猪拖到任意显示器的左、右、上或下方物理外边缘并松手；
- 主窗口会平滑收进屏幕外，只留下一个 68×68 的可点击尾巴窗口；
- 单击尾巴后猪猪会播放揭示动画并回到桌面；
- 多显示器内部接缝不会触发隐藏；
- Codex 开始工作、请求权限或完成任务时会自动恢复显示。

Windows 端的真实桌面回归测试可以运行：

```powershell
python .\tools\runtime_edge_smoke.py
```

## Codex Integration

Codex integration is implemented through hooks. Codex does not execute a new or
changed user hook until it has been reviewed. On macOS, run `codex` in Terminal,
enter `/hooks`, choose `Trust all and continue`, then restart Codex Desktop.

Event mapping:

| Codex hook event | Pig state |
| --- | --- |
| `SessionStart` | idle |
| `UserPromptSubmit` | thinking |
| `PreToolUse` | thinking |
| `PostToolUse` | thinking |
| `Stop` | success |
| `PermissionRequest` | permission |

When Codex enters `thinking`, the pig chases a carrot. When Codex emits `Stop`, the pig immediately plays the celebration animation and returns to idle.

Long Codex tasks can involve many tool calls. To avoid the pig getting stuck in carrot mode, the hook also uses a small local fallback watcher after `UserPromptSubmit`. The watcher reads Codex's local session records under `~\.codex\sessions` and only emits a synthetic success when the same `session_id + turn_id` clearly reaches `task_complete`. If no usable completion signal appears, thinking state eventually expires instead of staying forever.

## Claude Code Integration

Claude Code integration works the same way as the Codex integration above and
shares the same status bridge file, so the pet reacts to whichever CLI is
currently active. The installer (unless run with `-NoClaudeHooks`) writes the
hook wiring into `~\.claude\settings.json` (Windows only for now; macOS is not
covered yet). Restart any running `claude` session after installing so it
picks up the new hooks.

Event mapping:

| Claude Code hook event | Pig state |
| --- | --- |
| `SessionStart` | idle |
| `UserPromptSubmit` | thinking |
| `PreToolUse` | thinking |
| `PostToolUse` | thinking |
| `Stop` | success |
| `PermissionRequest` | permission |

`PreToolUse` and `PostToolUse` only update the pig's animation state; they
never return a permission decision, so they cannot affect whether a tool call
is allowed. Only `PermissionRequest` — which Claude Code fires exactly when it
would otherwise show its own permission prompt — can allow or deny a tool
call, and it does so through the pig's permission bubble described below. If
GooglePiggy is not running, the hook immediately escalates back to Claude
Code's normal permission prompt instead of blocking; the same happens if no
decision arrives within the hook's 10-minute timeout.

Unlike the Codex hook, the Claude Code hook does not need a fallback
completion watcher: Claude Code's `Stop` event already fires synchronously
when a turn actually finishes.

## Permission Bubble

When Codex or Claude Code triggers a real `PermissionRequest` hook, the pet switches to the question animation and shows a small bubble above the pig:

- click `允许` to send `allow` back to Codex or Claude Code;
- click `拒绝` to send `deny` back to Codex or Claude Code.

The permission bridge uses files under:

```text
%LOCALAPPDATA%\GifPigDesktopPet\permission-requests\
~/Library/Application Support/GifPigDesktopPet/permission-requests/
```

If the user already handled the permission inside Codex or Claude Code, or the request expires, the pet clears the bubble and returns to the normal state.

Manual preview:

```powershell
.\tools\preview-permission-ui.ps1 -Seconds 10
```

macOS:

```zsh
"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --preview-permission 10
```

If this preview works but a specific permission prompt does not appear on the pet, that prompt probably did not enter the `PermissionRequest` hook path and must still be handled inside Codex or Claude Code.

## Manual Status Testing

You can test the bridge without Codex:

```powershell
.\pig_pet.exe --bridge-event thinking
.\pig_pet.exe --bridge-event success
.\pig_pet.exe --bridge-event idle
```

Permission preview:

```powershell
.\tools\preview-permission-ui.ps1 -Seconds 10
```

macOS:

```zsh
"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --bridge-event thinking

"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --bridge-event success

"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --bridge-event idle
```

## Run From Source

Clone the repository:

```powershell
git clone https://github.com/Myf-ricey/GooglePiggy_DesktopPet.git
cd GooglePiggy_DesktopPet
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run:

```powershell
python .\pig_pet.py
```

Source mode creates generated folders when needed:

```text
cache/
qa/
```

These are build/test artifacts and are intentionally ignored by Git.

## Build A Windows ZIP

For local release builds:

```powershell
.\build-release.ps1
```

The build script will:

1. create or reuse `.venv-build`;
2. install build dependencies from `requirements-dev.txt`;
3. prepare transparent effect and edge-tail assets;
4. generate animation cache and QA outputs;
5. run source and edge-hiding smoke tests;
6. build the portable app with PyInstaller;
7. create a ZIP.

Outputs:

```text
dist\GifPigDesktopPet\
dist\GifPigDesktopPet-windows-x64.zip
```

## Build macOS ZIP and DMG

在 macOS 13+ 安装 Xcode Command Line Tools 后运行：

```zsh
./build-macos.sh
```

默认输出：

```text
dist/GooglePiggy-macos-universal.zip
dist/GooglePiggy-macos-universal.dmg
```

本地脚本默认交叉编译 Universal 2 应用。GitHub Actions 还会在对应硬件上分别构建并
测试 Apple Silicon (`arm64`) 和 Intel (`x64`) 版本。

## GitHub Actions Release

This repository includes:

```text
.github/workflows/windows-release.yml
.github/workflows/macos-release.yml
```

You can manually run either release workflow in GitHub Actions. A regular `v*` tag normally
builds both platforms. For a platform-only release such as `v0.3.2`, build and verify that
platform locally, then upload only its artifacts to the GitHub Release.

```powershell
git tag vNEXT
git push origin vNEXT
```

## Project Structure

```text
.
├─ .github/workflows/windows-release.yml
├─ .github/workflows/macos-release.yml
├─ assets/
│  ├─ effects/          # processed transparent sparkle/firework assets
│  ├─ edge-tail/         # four transparent tail assets for edge hiding
│  ├─ source-effects/   # original effect images
│  └─ source-gifs/      # source pig GIFs
├─ hooks/
│  ├─ codex-pig-hook.ps1
│  └─ claude-pig-hook.ps1
├─ tools/
│  ├─ prepare_effect_assets.py
│  ├─ preview-permission-ui.ps1
│  ├─ export_macos_assets.py
│  ├─ test_macos_release.py
│  ├─ package_github_source.py
│  ├─ prepare_edge_tail_assets.py
│  ├─ runtime_edge_smoke.py
│  └─ smoke_test.py
├─ releases/              # locally verified portable release packages
│  ├─ GifPigDesktopPet-windows-x64.zip
│  └─ GooglePiggy-macos-universal-v0.3.2.zip
├─ pig_pet.py
├─ macos/                  # native Swift/AppKit runtime and installer scripts
├─ build-macos.sh
├─ codex_bridge.py
├─ install.ps1
├─ uninstall.ps1
├─ build-release.ps1
├─ pig_pet.spec
├─ requirements.txt
├─ requirements-dev.txt
├─ requirements-macos-build.txt
├─ README-MAC.md
├─ RELEASE-NOTES-v0.3.2.md
├─ RELEASE-NOTES-v0.3.1.md
├─ RELEASE-NOTES-v0.2.2.md
├─ RELEASE-NOTES-v0.2.3.md
├─ RELEASE-NOTES-v0.3.0.md
└─ GITHUB-UPLOAD-GUIDE.md
```

## Troubleshooting

### macOS 上只有待机、点击和拖动，Codex 思考/完成没有反应

这通常表示 Hook 已安装但尚未信任。打开终端运行 `codex`，输入 `/hooks`，确认
GooglePiggy 的命令路径后完成信任，再完全重启 Codex 桌面版。只重启不会自动信任
用户 Hook。

### macOS 上取消右键菜单后猪猪消失

请升级到 `0.2.2` 或更高版本。新版不会在最后窗口暂时失去可见性时退出，并会在
右键菜单取消后主动恢复透明面板。

### macOS 权限气泡只显示一行，后半段变成省略号

请升级到 `0.2.3` 或更高版本。新版不会显示 `apply_patch` 或原始补丁协议，而是
解析真实工具输入，用自然中文说明创建、修改、删除等具体动作，并显示绝对路径、
应用名称或亮度值。当权限 Hook 未直接携带参数时，会按
`session_id + turn_id + 工具类型` 从 Codex 本地 session 记录恢复本次真实参数；
相对路径会依据任务工作目录还原。若异常情况下仍无法取得详情，猪猪不会显示模糊
授权问题，而会让 Codex 原生界面处理该次授权。恢复器兼容 JSON 与无引号
JavaScript 对象字段，也会解析终端命令中嵌套的文件补丁。正文按字符多行换行。

### macOS 阻止打开应用或安装脚本

按住 Control 点击 `install.command` 或 `GooglePiggy.app`，选择“打开”，再确认
一次。正式发布如使用 Developer ID 签名和 Apple 公证，可消除这一步。

### The pig keeps chasing the carrot

The pet is probably still seeing a recent `thinking` state from Codex. Newer hooks include a completion watcher and a stale-state timeout. If it still happens, check:

```text
%LOCALAPPDATA%\GifPigDesktopPet\codex-status.json
%LOCALAPPDATA%\GifPigDesktopPet\pig-heartbeat.json
~/Library/Application Support/GifPigDesktopPet/codex-status.json
~/Library/Application Support/GifPigDesktopPet/pig-heartbeat.json
```

### Permission bubble does not appear

Run:

```powershell
.\tools\preview-permission-ui.ps1 -Seconds 10
```

macOS 可运行：

```zsh
"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --preview-permission 10
```

If preview works, the pet UI is fine. The specific Codex prompt may not be emitted as a `PermissionRequest` hook.

### Chinese text shows as squares

The app tries Windows CJK fonts such as Microsoft YaHei and SimHei. If those fonts are missing or disabled, install a CJK-capable font and restart the pet.

## Assets And License

Code is released under the MIT License. See `LICENSE`.

The pig GIFs and decorative assets under `assets/` have been confirmed by the project maintainer as redistributable with this open-source project. Code license and asset permission are documented separately; see `ASSET-NOTICE.md`.
