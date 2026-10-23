# GooglePiggy Desktop Pet for macOS

这是 GooglePiggy 猪猪桌宠的原生 macOS 版。当前发布版本为 `0.5.6`。它会陪你
观察 Codex 的工作状态，也会在空闲时悄悄躲到屏幕边缘：

- 呼吸待机、点击躺平、拖动左拱；
- 空闲时拖到桌面边缘会弹跳入边，只留下贴住物理屏幕边缘的可点击小猪尾巴；
  点一下尾巴，猪猪就会跳回来；
- 尾巴进出使用与 Windows 端一致的 60Hz 平滑短动画，能看到猪猪短暂地滑入和滑出；
- Codex 思考时追胡萝卜，完成时跳跃并显示火花/烟花；
- Codex 权限请求气泡，以及“允许/拒绝”回传；
- 右键状态互动、休息模式、开机自启动、Hook 授权说明和退出；
- 透明、无边框、置顶，并可显示在所有桌面空间；
- 便携应用包，运行时不需要 Python、PowerShell 或 Homebrew。

自 `v0.4.0` 起支持：新增多任务状态展示、看书与整理文件动画、随机睡眠和偷吃胡萝卜；切换任务时保留各自的动画进度。Windows 版本不受本次更新影响。

## v0.5.6 更新

- 新增外观设置：独立调整桌宠、对话框和任务栏大小、文字/背景颜色、背景/按钮透明度与间距。
- 预览在桌宠实际位置显示，恢复默认保留预览勾选；默认对话框保留原有奶油到浅粉渐变。
- 任意状态的任务均可点击打开对话；灯泡、分层动画与隐藏尾巴随猪猪整体缩放。
- [发布说明](RELEASE-NOTES-v0.5.6-macos.md)。Windows 对应功能待移植和实机验收，现有 0.5.5 修复保持不变。

## v0.5.3 更新

- 运行中拖到边缘隐藏后，持续隐藏直到对应任务及子任务完成，再弹出完整庆祝；点击尾巴仍可提前唤出。
- 动画切换、子任务启动、其他任务变化和更新提示不会提前解除上述隐藏。
- 精确过滤已识别的 Codex 建议安全检查后台请求，保留正常线程、未命名任务和真实子任务。
- [0.5.3 发布说明](RELEASE-NOTES-v0.5.3-macos.md)。

## v0.5.2 更新

- 过滤首页推荐任务、Claudian 自动标题生成和已识别的 Codex 记忆整理内部会话，避免误触发工作动画。
- 清理内部会话的启动占位，忽略迟到事件；重启回放也不会恢复这些残留线程。
- 保留正常用户任务及真实子任务；记忆整理识别同时要求固定提示词与专用目录，不开启 Codex memories。
- [0.5.2 发布说明](RELEASE-NOTES-v0.5.2-macos.md)。

## v0.5.1 更新

- 点击「更新」即可在气泡中下载安装，校验通过后备份旧版并覆盖重启。
- 新增下载进度、取消、失败重试；权限请求未处理完时延后重启。
- [0.5.1 发布说明](RELEASE-NOTES-v0.5.1-macos.md)。

## v0.5.0 更新

- 每次启动后台检查 Mac 正式版；右键「检查更新…」也可主动检查。
- 有新版时，猪头上方显示暖黄色发光灯泡和更新气泡，提供「稍后再说 / 更新」。
- 手动检查无新版时显示「当前已是最新版本啦！」；后台无新版或网络失败时不打扰。
- 包含 2026-10-11 的建议回复内部会话过滤修复，以及 2026-10-07 的左拱动画残余灰色地面影子清理。

完整说明见 [macOS 0.5.0 发布说明](RELEASE-NOTES-v0.5.0-macos.md)。

回归测试（macOS，需要 Xcode Command Line Tools）：

```sh
swiftc -framework AppKit macos/Sources/GooglePiggy/AppSupport.swift macos/Sources/GooglePiggy/FamilyStore.swift tests/suggested-replies/main.swift -o /tmp/googlepiggy-suggested-replies-test
/tmp/googlepiggy-suggested-replies-test
```

测试使用临时 Codex 元数据和桌宠状态，覆盖预测请求、迟到事件、重启回放，以及真实线程/子代理不被误过滤。

## 系统要求

- macOS 13 Ventura 或更高版本；
- 优先下载同时支持两类处理器的 `GooglePiggy-macos-universal`；
- 也可以下载与 Mac 处理器匹配的较小发布包：
  - `GooglePiggy-macos-arm64`：Apple Silicon（M1/M2/M3/M4/M5 等）；
  - `GooglePiggy-macos-x64`：Intel Mac。

下载：[macOS v0.5.6 通用安装包](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/tag/v0.5.6-macos)。

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
- 右键猪猪：切换 Codex 联动、进入休息模式、开关自启动或退出。
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

构建机需要 Xcode Command Line Tools、Keka（用于 ZIP 打包）和 Python 3.11+：

```zsh
chmod +x build-macos.sh
./build-macos.sh
```

构建使用仓库中 `assets/macos-resources` 的最终帧资源，然后编译原生 Swift
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

## 自动休息与偷吃胡萝卜

状态互动模式下，每轮清醒抽取一次睡眠等待时间：截断正态分布，均值约 10 分钟、标准差约 2.965 分钟，范围 3～30 分钟；约一半落在 8～12 分钟。新的 Codex 任务重新计时，普通点击躺平和清醒期间的拖动均不重置。拖动期间到达睡眠时点时，保留原截止时间，松手后再进入睡觉；若此时出现 Codex 任务，则先处理任务。任务、权限、拖动、拱动和其他临时动作均优先于休闲动作。

睡着后点击：50% 左拱完整两次，回到待机并重新抽取下一轮；50% 仅摇尾巴继续睡，ZZZ 的时钟不中断。睡中点击不会触发躺平。

每轮在开始时抽取偷吃计划：只在 1/3 时点吃占 40%，只在 2/3 时点吃占 40%，两次都吃占 10%，不吃占 10%。忙碌时错过的吃饭时点不补播；偷吃可被点击躺平、拖动和 Codex 动作打断。

右键 **休息模式** 无须等倒计时，直接开始睡觉，并保留上述互动和 Codex 优先级；忙碌时此项不可用。菜单已移除全部动画预览项。

线程动画按线程 ID 和任务回合维护独立的单调时钟，未选中时仍推进。切换回来显示当前帧，不重播入场；同一回合从工具执行回到看书时保留看书进度，拿书播完后只循环阅读段。新回合重置该线程动画；后台已经结束的完成动画不会因切换重播。

## v0.4.0 升级

安装器将旧的 `~/Applications/GooglePiggy.app` 保留到 `~/Applications/GooglePiggy Backups/时间戳/`，新版本使用正式应用路径并接管自启动和 Codex hooks。旧应用不再自动启动。用户状态仍保存在 `~/Library/Application Support/GifPigDesktopPet/`。

正式菜单不再显示动画预览。偷吃采用新版横向像素胡萝卜，包含左右张望、视线高低变化及前半身轻微压缩；睡眠保留打哈欠、趴下回弹、独立 ZZZ 和点击摆尾。

## 检查更新

Mac 版每次启动在后台检查一次正式 macOS Release；没有新版或后台网络失败时不弹窗。
右键「检查更新…」可主动检查：有新版显示发光灯泡、更新重点、版本变化及
「稍后再说 / 更新」；没有新版显示「当前已是最新版本啦！」和「收到！」。
手动检查网络失败会明确提示，不会当作已经是最新版。

「更新」在应用内下载新版、校验签名、备份旧版并覆盖重启。下载时可以取消，失败后可以重试。
0.5.0 及更早版本需要手动安装一次 0.5.1，之后才能一键安装后续版本。
「稍后再说」关闭本次提示，下次启动重新检查。真实 Codex 权限对话框优先，更新提示会在权限处理后恢复。
发布需使用 `v数字版本-macos` 标签、非预发布状态，并附带非空 macOS 安装包；Windows Release 不参与比较。
Release 正文前三个列表项用于更新重点，建议每项写一句简短的用户可读说明。

开发预览（使用固定演示数据，不代表在线检查结果）：

```sh
swiftc -framework AppKit macos/Sources/GooglePiggy/UpdateNotice.swift tests/update-preview/main.swift -o /tmp/googlepiggy-update-preview
/tmp/googlepiggy-update-preview --live
```

演示窗口按钮用于切换「发现新版 / 已是最新」两种状态，不下载、不安装。
预览同时输出 PNG 与动画 GIF 至 `build/update-preview/`。
完整应用可用 `--preview-update available`、`--preview-update current` 或 `--preview-update error` 预览。

更新逻辑回归：

```sh
swiftc -framework AppKit macos/Sources/GooglePiggy/UpdateNotice.swift tests/update-checker/main.swift -o /tmp/googlepiggy-update-test
/tmp/googlepiggy-update-test
```

## 一键更新（0.5.1 起）

0.5.1 已接入 Sparkle 2.10.0。点击「更新」后，气泡显示下载和校验进度，
下载时可以取消；安装前备份旧应用，再退出、原位替换并重启。权限请求未处理完时延后重启。
失败时保留原版并显示原因，可重试。安装目录须可写，不能从 DMG 或 App Translocation 中更新。

0.5.0 用户需手动安装一次 0.5.1，后续版本才能一键安装。
签名私钥留在发布者本机钥匙串，账户名 `GooglePiggyDesktopPet`；源码只包含公钥。
每个 Release 必须额外附带 `appcast.xml` 和 `GooglePiggy-macos-update-版本.zip`，
由 `tools/package_macos_update.sh` 生成签名清单和只含应用的更新包。
完整发布顺序及签名说明见 [一键更新发布指南](macos/UPDATE-RELEASE.md)。



### 外观设置

右键桌宠，在菜单选择“外观…”。桌宠、对话框、任务栏可独立调整为 50%–200%；对话框和任务栏可选择颜色及 10%–100% 不透明度。文字、按钮与间距随所属框同步缩放，设置即时生效并自动保存。“恢复默认”可重置所有外观设置。对话框设置同时用于权限确认和更新提示。

外观回归检查：

```sh
swiftc -framework AppKit macos/Sources/GooglePiggy/AppSupport.swift macos/Sources/GooglePiggy/FamilyStore.swift macos/Sources/GooglePiggy/FamilySelector.swift macos/Sources/GooglePiggy/UpdateNotice.swift macos/Sources/GooglePiggy/AppearancePreview.swift tests/appearance/main.swift -o /tmp/googlepiggy-appearance-tests
/tmp/googlepiggy-appearance-tests
```

点击任务栏中的任意任务都会打开对应的 Codex 对话，包括进行中、等待权限和已完成的任务。已完成任务的未读蓝点仍在 Codex 确认已读后消失。

外观面板中的“预览对话框”和“预览任务栏”可分别勾选，在桌宠实际的对话框和任务栏位置持续显示示例，随桌宠移动、缩放并实时更新外观。取消勾选或关闭外观面板会收起预览，示例不影响真实任务或已读状态。

框透明度设置仅影响框背景和边框，独立的“按钮不透明度”滑条控制按钮底色；标题、正文、任务名称和按钮文字保持不透明，实际界面与预览一致。

默认对话框保留原版奶油色至浅粉色渐变与玫瑰色边框。恢复默认仅重置外观参数，保留预览勾选和设置窗口位置。

支持独立设置对话框文字、按钮文字颜色。对话框间距偏移可在原位置基础上向近处或远处调整（−80～200 pt，默认 0）；任务栏间距为 0～200 pt（默认 8）。字体保持不透明，实际显示、按钮点击区域与预览同步更新。
