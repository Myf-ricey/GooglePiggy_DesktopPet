# GooglePiggy Desktop Pet

一个 Windows 透明桌面宠物。它直接使用 GIF 原始帧生成动画，并可通过 Codex hooks 感知 Codex 当前状态：思考时追胡萝卜，回答结束时跳跳庆祝。

## 功能

- 空闲：循环播放轻微呼吸待机动画。
- 左键单击：没有其他动作时播放一次躺平动画。
- 鼠标拖动：拖动期间播放左拱动画。
- Codex 工作中：播放追胡萝卜动画。
- Codex 回答结束：播放跳跳猪，并显示少量亮晶晶和烟花点缀。
- 右键菜单：动作预览、开机自启动开关、退出。
- 可选 Codex hooks：自动把 Codex 生命周期事件同步到桌宠状态。

## 系统兼容性

- 支持：Windows 10/11 x64。
- 便携版不要求用户安装 Python。
- 源码运行需要 Python 3.11+，推荐 Python 3.13。
- 安装脚本写入的是当前用户注册表和当前用户的 Codex 配置，不需要管理员权限。
- 程序状态文件位于 `%LOCALAPPDATA%\GifPigDesktopPet\codex-status.json`。
- macOS 和 Linux 暂不支持，因为桌宠窗口使用 Windows layered window API。

## 给普通用户：安装便携版

从 GitHub Releases 下载：

```text
GifPigDesktopPet-windows-x64.zip
```

解压后，在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

安装脚本会：

- 创建桌面快捷方式。
- 开启当前用户的开机自启动。
- 将猪猪 Codex hook 添加到 `~\.codex\hooks.json`。
- 启动桌宠。

如果不想安装 Codex hooks：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoCodexHooks
```

如果只想临时启动，不安装：

```powershell
.\start-pig-pet.cmd
```

卸载当前用户的自启动、桌面快捷方式和本项目添加的 Codex hooks：

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

卸载脚本不会删除程序文件夹。

## Codex Hook 说明

安装 hooks 后，需要重启 Codex。Codex 首次看到新 hook 时会要求你确认信任，这是安全机制。

事件映射：

- `SessionStart` -> `idle`
- `UserPromptSubmit` -> `thinking`
- `PreToolUse` -> `thinking`
- `PostToolUse` -> `thinking`
- `Stop` -> `success`

桌宠收到 `thinking` 后播放追胡萝卜；收到 `success` 后播放跳跳庆祝，再回到呼吸待机。新版 hook 还会在 `UserPromptSubmit` 后启动一个隐藏的轻量兜底监听器：如果 Codex 没有发出 `Stop` hook，它会读取当前用户的 `~\.codex\sessions` 本地会话记录，只在同一个 `session_id + turn_id` 出现明确的 `task_complete` 时补写 `success`，因此长任务不会被误判成完成。若本地记录也不可用，`thinking` 才会在一段时间后自动过期回到待机，避免一直卡在胡萝卜。

手动测试状态桥：

```powershell
.\pig_pet.exe --bridge-event thinking
.\pig_pet.exe --bridge-event success
.\pig_pet.exe --bridge-event idle
```

如果 Codex 信任按钮点了又弹回，检查 `C:\Users\<你>\.codex\config.toml` 是否被设置成只读。

## 给开发者：源码运行

克隆仓库后：

```powershell
python -m pip install -r requirements.txt
python .\pig_pet.py
```

源码模式会在首次运行或 QA 时自动生成：

```text
cache/
qa/
```

这些是生成产物，不需要提交到 GitHub。

## 本地构建 Windows 便携包

```powershell
.\build-release.ps1
```

构建脚本会：

1. 创建或复用 `.venv-build`。
2. 安装构建依赖。
3. 处理透明装饰素材。
4. 生成动画缓存和 QA 报告。
5. 运行烟测。
6. 用 PyInstaller 构建 Windows 便携文件夹。
7. 输出 ZIP。

产物位置：

```text
dist\GifPigDesktopPet\
dist\GifPigDesktopPet-windows-x64.zip
```

## GitHub Actions 发布

仓库包含：

```text
.github/workflows/windows-release.yml
```

你可以：

- 在 GitHub Actions 手动运行 `Build Windows release`。
- 推送 `v*` 标签自动构建并把 ZIP 附到 GitHub Release。

示例：

```powershell
git tag v0.1.0
git push origin v0.1.0
```

## 项目结构

```text
.
├─ .github/workflows/windows-release.yml
├─ assets/
│  ├─ effects/          # 已处理透明装饰图
│  ├─ source-effects/   # 原始装饰图
│  └─ source-gifs/      # 猪猪 GIF 源素材
├─ hooks/
│  └─ codex-pig-hook.ps1
├─ tools/
│  ├─ prepare_effect_assets.py
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

## 素材与授权

程序代码使用 MIT License，见 `LICENSE`。

`assets/` 下的猪猪 GIF 和装饰图片已由项目维护者确认可以随本项目开源再分发。程序代码许可证和素材授权仍分开说明，更多细节见 `ASSET-NOTICE.md`。
