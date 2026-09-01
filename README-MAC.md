# GooglePiggy Desktop Pet for macOS

这是 GooglePiggy 猪猪桌宠的原生 macOS 版。当前发布版本为 `0.3.2`。它会陪你
观察 Codex 的工作状态，也会在空闲时悄悄躲到屏幕边缘：

- 呼吸待机、点击躺平、拖动左拱；
- 空闲时拖到桌面边缘会弹跳入边，只留下贴住物理屏幕边缘的可点击小猪尾巴；
  点一下尾巴，猪猪就会跳回来；
- 尾巴进出使用与 Windows 端一致的 60Hz 平滑短动画，能看到猪猪短暂地滑入和滑出；
- Codex 思考时追胡萝卜，完成时跳跃并显示火花/烟花；
- Codex 权限请求气泡，以及“允许/拒绝”回传；
- 右键动作预览、开机自启动和退出；
- 透明、无边框、置顶，并可显示在所有桌面空间；
- 便携应用包，运行时不需要 Python、PowerShell 或 Homebrew。

`v0.3.2` 是跨平台尾巴隐藏版本：Windows 和 macOS 都支持四个物理外边缘的尾巴形态
隐藏、点击尾巴跳回，以及工作状态触发的自动恢复。Windows 版可从主 README 中的
便携包链接下载。

## 系统要求

- macOS 13 Ventura 或更高版本；
- 优先下载同时支持两类处理器的 `GooglePiggy-macos-universal-v0.3.2`；
- 也可以下载与 Mac 处理器匹配的较小发布包：
  - `GooglePiggy-macos-arm64`：Apple Silicon（M1/M2/M3/M4/M5 等）；
  - `GooglePiggy-macos-x64`：Intel Mac。

## 推荐安装

1. 解压 ZIP，或打开 DMG 后把完整发布文件夹复制到本地。
2. 双击 `install.command`。
3. 安装器会把 `GooglePiggy.app` 复制到 `~/Applications/`、启用当前用户
   开机自启动、安装 Codex hooks，并启动猪猪。
4. 首次安装后打开“终端”，运行 `codex`；进入后输入 `/hooks`，选择
   `Trust all and continue`。
5. 退出终端版 Codex，再重启 Codex 桌面版。

Codex 会把新写入的用户 Hook 标记为“未信任”，在你确认前不会执行。只重启
Codex 不会跳过这项安全检查。更新桌宠后如果 Hook 命令发生变化，Codex 可能会
要求再次确认。

在 `/hooks` 页面先核对命令是否指向：

```text
~/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy --hook
```

如果页面中还有其他来源不明的 Hook，请只信任 GooglePiggy 对应项。

如果 macOS 第一次拦截未公证的开源应用或脚本，请在 Finder 中按住 Control 点击
`install.command`（或 `GooglePiggy.app`），选择“打开”，再确认一次。公开发布前
如使用 Apple Developer 证书签名并公证，可去掉这一步。

安装器可选参数：

```zsh
./install.command --no-autostart
./install.command --no-codex-hooks
./install.command --no-start
```

只想临时运行时，可以直接双击 `GooglePiggy.app`。

## 首次验证

安装、信任 Hook 并重启 Codex 桌面版后：

1. 给 Codex 发送一条新任务，猪猪应在思考期间追胡萝卜。
2. Codex 完成回答后，猪猪应跳跃并显示火花/烟花。
3. 单击猪猪，应播放一次躺平动画。
4. 拖动猪猪，应播放左拱动画并跟随鼠标。
5. 空闲时把猪猪拖到任一桌面外边缘并松手，应跳入边缘且只露出尾巴；
   尾巴应与物理屏幕边缘相接，不能悬浮在 Dock 的工作区边界，露出的臀部应为
   带描边的圆弧，不应出现直线裁切痕迹。单击尾巴后应以待机猪的弹跳/拉伸动作跳回，
   并与可用工作区边缘保留一小段距离。从底边跳回时，最终位置应再向下移动
   1 个当前猪猪的非透明内容高度。
   隐藏和跳回都应能看到短暂、连续的滑动过程，而不是瞬间消失或出现。
6. Codex 思考或请求权限时，猪猪不应进入隐藏状态；如果任务在隐藏期间开始，
   猪猪应自动跳出并显示对应状态。
7. 右键打开菜单后点击空白处取消，猪猪应继续显示。
8. 当 Codex 请求权限时，说明文字应自动换行，并可通过“允许/拒绝”回传。

## 使用

- 单击猪猪：在空闲状态播放一次躺平动画。
- 按住并拖动：猪猪播放左拱动画并跟随鼠标。
- 空闲时拖到屏幕外边缘并松手：猪猪跳入边缘，只露出尾巴；单击尾巴可跳回。
- 右键猪猪：切换 Codex 联动、预览任一动作、开关自启动或退出。
- 如果 Codex 联动没有反应：右键选择“Codex Hook 首次授权说明…”。
- Codex 请求权限：点击气泡中的“允许”或“拒绝”。

运行状态保存在：

```text
~/Library/Application Support/GifPigDesktopPet/
```

## 手工测试 Codex 状态

```zsh
"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --bridge-event thinking

"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --bridge-event success

"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --bridge-event idle
```

权限气泡预览：

```zsh
"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --preview-permission 10
```

预览期间点击“允许”或“拒绝”，终端会输出桌宠收到的选择。

四向触边视觉预览（先退出正在运行的猪猪；方向可换成 `left/right/top/bottom`）：

```zsh
"$HOME/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy" \
  --preview-edge-hide right
```

## 常见问题

### 只有待机、点击、拖动动画，Codex 联动没有反应

Hook 尚未完成信任。运行终端版 `codex`，输入 `/hooks`，信任 GooglePiggy 的
Hook 后完全重启 Codex 桌面版。只重启不会自动信任。

### 取消右键菜单后猪猪消失

`0.2.2` 已加入两层保护：最后一个透明面板暂时关闭时应用不会退出；右键菜单结束
后会主动恢复窗口。旧版本请直接运行新版 `install.command` 覆盖安装。

### 权限说明后半段过早显示省略号

请升级到 `0.2.3` 或更高版本。新版会解析真实工具输入并转换成自然中文，说明
准备执行的具体操作、绝对路径、应用名称或亮度值。如果权限 Hook 没有直接携带
参数，桌宠会按同一任务、回合和工具类型从 Codex 本地 session 记录恢复真实参数，
相对路径也会依据该任务的工作目录还原成绝对路径。只有在两处都无法取得详情的
异常情况下，猪猪才不接管该次授权，交由 Codex 原生授权界面处理；不会显示空泛
问题让用户盲目允许。恢复器兼容 Codex 的 JSON 与 JavaScript 对象参数格式，也能
识别终端命令内嵌套的文件补丁。正文按字符多行换行，并扩展了详细权限说明区域。

### macOS 提示无法验证开发者或阻止打开

按住 Control 点击 `install.command` 或 `GooglePiggy.app`，选择“打开”，再确认
一次。这是 ad-hoc 签名、尚未经过 Apple 公证的开源测试包的正常首次提示。

### 查看运行状态

```text
~/Library/Application Support/GifPigDesktopPet/codex-status.json
~/Library/Application Support/GifPigDesktopPet/pig-heartbeat.json
~/Library/Application Support/GifPigDesktopPet/codex-hook-events.jsonl
```

Codex 官方 App 更新后如果出现联动回退，可运行：

```zsh
python3 tools/codex_hook_snapshot.py
```

协议基线、日志路径和分层定位步骤见
[CODEX-HOOK-COMPATIBILITY.md](CODEX-HOOK-COMPATIBILITY.md)。

## 卸载

双击发布文件夹内的 `uninstall.command`。它会移除：

- `~/Applications/GooglePiggy.app`；
- 当前用户的开机自启动项；
- 本项目写入 `~/.codex/hooks.json` 的 hooks。

它不会删除运行状态，也不会删除其他项目的 Codex hooks。

## 从源码构建

构建机需要 Xcode Command Line Tools 和 Python 3.11+：

```zsh
chmod +x build-macos.sh
./build-macos.sh
```

构建会复用 Windows 版同一套动画清理、尺寸归一和锚点算法，然后编译原生 Swift
应用、做 ad-hoc 签名、运行黑盒测试，并生成：

```text
dist/GooglePiggy-macos-universal.zip
dist/GooglePiggy-macos-universal.dmg
```

默认构建输出为 `GooglePiggy-macos-universal`。设置 `BUILD_UNIVERSAL=0` 时，
Apple Silicon 构建机会生成 `arm64` 文件名，Intel 构建机会生成 `x64` 文件名。

## 发布签名

本地构建默认使用 ad-hoc 签名，适合测试和开源分发。正式发布建议用你的
Developer ID Application 证书签名并提交 Apple notarization；这只影响
Gatekeeper 信任体验，不影响桌宠功能。
