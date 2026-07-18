# GooglePiggy Desktop Pet

一只会陪你和 Codex 一起工作的 Windows / macOS 桌面小猪。

它不是简单贴在屏幕上的静态图片，而是一个透明置顶的小桌宠：平时轻轻呼吸，拖动时会左拱，点一下会躺平；当 Codex 正在工作时，它会追胡萝卜；任务完成时，它会跳起来庆祝，还会撒一点亮晶晶和小烟花。遇到 Codex 权限请求时，它会变成疑问猪，在头顶弹出允许/拒绝气泡，并把选择传回 Codex。

这个项目最早只是一个“我想让工作状态变得更可爱一点”的小点子。现在它被整理成了一个可以开源、可以安装、可以继续改造的完整跨平台小工具。

## Features

- Idle: 循环播放很轻微的呼吸动画。
- Left click: 没有其他动作时，播放一次躺平动画。
- Dragging: 拖动猪猪时播放左拱动画。
- Codex thinking: Codex 工作或思考时，播放追胡萝卜动画。
- Codex success: Codex 完成回答时，播放跳跳猪庆祝动画，并显示小火花和烟花。
- Codex permission: Codex 请求权限时，播放疑问猪，并显示允许/拒绝气泡。
- Right-click menu: 支持动作预览、开机自启动开关、退出。
- Portable build: Windows 便携版不要求用户安装 Python。
- Native Mac build: macOS 版是原生透明 AppKit 应用，运行时同样不要求 Python。
- Open-source ready: 源码、素材、构建脚本、GitHub Actions workflow 都在仓库里。

## Compatibility

| Item | Status |
| --- | --- |
| Windows 10/11 x64 | Supported |
| macOS 13+ Apple Silicon | Supported |
| macOS 13+ Intel | Supported |
| Portable ZIP | Supported |
| macOS DMG | Supported |
| Python source run | Python 3.11+, tested with Python 3.13 |
| Codex hooks | Optional |
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
GooglePiggy-macos-universal.zip # Apple Silicon + Intel
GooglePiggy-macos-universal.dmg
```

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

Download the Windows release ZIP from GitHub Releases:

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
- start the desktop pet.

If you only want the pet and do not want Codex integration:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoCodexHooks
```

If you only want to run it temporarily:

```powershell
.\start-pig-pet.cmd
```

To uninstall the current-user shortcut, autostart entry, and hooks added by this project:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

The uninstall script does not delete the extracted program folder itself.

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

## Permission Bubble

When Codex triggers a real `PermissionRequest` hook, the pet switches to the question animation and shows a small bubble above the pig:

- click `允许` to send `allow` back to Codex;
- click `拒绝` to send `deny` back to Codex.

The permission bridge uses files under:

```text
%LOCALAPPDATA%\GifPigDesktopPet\permission-requests\
~/Library/Application Support/GifPigDesktopPet/permission-requests/
```

If the user already handled the permission inside Codex, or the request expires, the pet clears the bubble and returns to the normal state.

Manual preview:

```powershell
.\tools\preview-permission-ui.ps1 -Seconds 10
```

macOS:

```zsh
"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --preview-permission 10
```

If this preview works but a specific Codex permission prompt does not appear on the pet, that prompt probably did not enter the `PermissionRequest` hook path and must still be handled inside Codex.

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
3. prepare transparent effect assets;
4. generate animation cache and QA outputs;
5. run smoke tests;
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

You can manually run `Build Windows release` in GitHub Actions, or create a tag to build and attach the ZIP to a GitHub Release:

```powershell
git tag v0.2.3
git push origin v0.2.3
```

## Project Structure

```text
.
├─ .github/workflows/windows-release.yml
├─ .github/workflows/macos-release.yml
├─ assets/
│  ├─ effects/          # processed transparent sparkle/firework assets
│  ├─ source-effects/   # original effect images
│  └─ source-gifs/      # source pig GIFs
├─ hooks/
│  └─ codex-pig-hook.ps1
├─ tools/
│  ├─ prepare_effect_assets.py
│  ├─ preview-permission-ui.ps1
│  ├─ export_macos_assets.py
│  ├─ test_macos_release.py
│  ├─ package_github_source.py
│  └─ smoke_test.py
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
├─ RELEASE-NOTES-v0.2.2.md
├─ RELEASE-NOTES-v0.2.3.md
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
