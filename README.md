# GooglePiggy Desktop Pet

一只会陪你和 Codex 一起工作的 Windows 桌面小猪。

它不是简单贴在屏幕上的静态图片，而是一个透明置顶的小桌宠：平时轻轻呼吸，拖动时会左拱，点一下会躺平；当 Codex 正在工作时，它会追胡萝卜；任务完成时，它会跳起来庆祝，还会撒一点亮晶晶和小烟花。遇到 Codex 权限请求时，它会变成疑问猪，在头顶弹出允许/拒绝气泡，并把选择传回 Codex。

这个项目最早只是一个“我想让工作状态变得更可爱一点”的小点子。现在它被整理成了一个可以开源、可以安装、可以继续改造的完整 Windows 小工具。

## Features

- Idle: 循环播放很轻微的呼吸动画。
- Left click: 没有其他动作时，播放一次躺平动画。
- Dragging: 拖动猪猪时播放左拱动画。
- Codex thinking: Codex 工作或思考时，播放追胡萝卜动画。
- Codex success: Codex 完成回答时，播放跳跳猪庆祝动画，并显示小火花和烟花。
- Codex permission: Codex 请求权限时，播放疑问猪，并显示允许/拒绝气泡。
- Right-click menu: 支持动作预览、开机自启动开关、退出。
- Portable build: Windows 便携版不要求用户安装 Python。
- Open-source ready: 源码、素材、构建脚本、GitHub Actions workflow 都在仓库里。

## Compatibility

| Item | Status |
| --- | --- |
| Windows 10/11 x64 | Supported |
| Portable ZIP | Supported |
| Python source run | Python 3.11+, tested with Python 3.13 |
| Codex hooks | Optional |
| macOS/Linux | Not supported yet |

The desktop window uses Windows layered-window APIs, so macOS and Linux are not supported in this version.

Runtime state is stored under:

```text
%LOCALAPPDATA%\GifPigDesktopPet\
```

The main status file is:

```text
%LOCALAPPDATA%\GifPigDesktopPet\codex-status.json
```

## Quick Start For Users

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

Codex integration is implemented through hooks. After installation, restart Codex. The first time Codex sees the hook, it may ask you to trust it. This is expected.

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
```

If the user already handled the permission inside Codex, or the request expires, the pet clears the bubble and returns to the normal state.

Manual preview:

```powershell
.\tools\preview-permission-ui.ps1 -Seconds 10
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

## GitHub Actions Release

This repository includes:

```text
.github/workflows/windows-release.yml
```

You can manually run `Build Windows release` in GitHub Actions, or create a tag to build and attach the ZIP to a GitHub Release:

```powershell
git tag v0.1.3
git push origin v0.1.3
```

## Project Structure

```text
.
├─ .github/workflows/windows-release.yml
├─ assets/
│  ├─ effects/          # processed transparent sparkle/firework assets
│  ├─ source-effects/   # original effect images
│  └─ source-gifs/      # source pig GIFs
├─ hooks/
│  └─ codex-pig-hook.ps1
├─ tools/
│  ├─ prepare_effect_assets.py
│  ├─ preview-permission-ui.ps1
│  └─ smoke_test.py
├─ pig_pet.py
├─ codex_bridge.py
├─ install.ps1
├─ uninstall.ps1
├─ build-release.ps1
├─ pig_pet.spec
├─ requirements.txt
└─ requirements-dev.txt
```

## Troubleshooting

### Codex asks me to trust the hook

This is normal after installing or changing hooks. Trust it once, then restart Codex if the hook list still looks stale.

### The pig keeps chasing the carrot

The pet is probably still seeing a recent `thinking` state from Codex. Newer hooks include a completion watcher and a stale-state timeout. If it still happens, check:

```text
%LOCALAPPDATA%\GifPigDesktopPet\codex-status.json
%LOCALAPPDATA%\GifPigDesktopPet\pig-heartbeat.json
```

### Permission bubble does not appear

Run:

```powershell
.\tools\preview-permission-ui.ps1 -Seconds 10
```

If preview works, the pet UI is fine. The specific Codex prompt may not be emitted as a `PermissionRequest` hook.

### Chinese text shows as squares

The app tries Windows CJK fonts such as Microsoft YaHei and SimHei. If those fonts are missing or disabled, install a CJK-capable font and restart the pet.

## Assets And License

Code is released under the MIT License. See `LICENSE`.

The pig GIFs and decorative assets under `assets/` have been confirmed by the project maintainer as redistributable with this open-source project. Code license and asset permission are documented separately; see `ASSET-NOTICE.md`.
