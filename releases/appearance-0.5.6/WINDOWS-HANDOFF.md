# 外观与任务跳转更新：Mac → Windows 交接

## 状态与基准

- 交接日期：2026-10-23（Asia/Shanghai）。已实际 fetch GitHub `main`。
- 最新远端基准完整 commit：`1ff99b35d5ae790b51e2dc568747ca3eaeb7fbae`，含 Windows 0.5.5 输入响应与历史中断子任务修复。
- GitHub：[仓库](https://github.com/Myf-ricey/GooglePiggy_DesktopPet)，分支 `codex/appearance-windows-handoff`。交接提交、PR 地址见 ZIP 内 `SOURCE.json`。
- 本轮共同目标：0.5.6。Mac 交接候选 **0.5.6 / 构建 11**，原发布版为 Mac 0.5.3 / 构建 10；Windows 保持已发布 **0.5.5 / 20261019.5-input-release**。
- 候选不是正式 Release，不存在已发布的 0.5.6 更新 feed；禁止把候选标记为正式更新可用。
- **Windows 实机待验收**。本包提供 Mac 实现、原始素材、代码落点和测试证据；没有替 Windows 实现或验证新增功能。

## 本线程已完成的行为

1. 右键菜单“外观…”：桌宠、对话框、任务栏独立缩放，字体和按钮随所属框同比例缩放，实时保存。
2. 框背景透明度与按钮底色透明度分开；文字始终不透明。对话框文字和按钮文字可独立选色。
3. 对话框和任务栏背景可选色。默认对话框保留原版奶油色→浅粉色渐变、玫瑰色边框，不能把默认色替换成纯白或单色。
4. 对话框、任务栏各有预览勾选，使用真实渲染器，在猪猪实际显示位置预览，随猪猪移动与缩放；示例不产生真实任务或已读变更。关闭外观窗口收起预览。
5. 恢复默认只重置外观参数，保留两个预览勾选和窗口位置。
6. 对话框相对原位置的上下偏移、任务栏与猪猪的距离可独立调节。绘制、点击、屏幕边缘限制使用同一变换。
7. 点击任意任务都打开对应 Codex 对话，不再限定“已完成且未读”；已有任务选择及未读机制保留。
8. 灯泡与全部宠物动画为一体：灯泡、睡眠身体/尾巴/Z、庆祝特效、小助手、隐藏大小尾巴跟随宠物比例；灯泡不受对话框大小、间距、透明度影响。

## 参数与默认值

Mac 存储键前缀 `appearance.`；Windows 可使用独立原子写入 JSON，禁止覆盖原有状态/自启动/更新数据。RGB 颜色与 alpha 分开保存。

| 键 | 取值 | 默认 | 语义 |
|---|---|---|---|
| petScale | 0.5–2 | 1 | 猪猪与所有动画装饰整体缩放 |
| dialogScale | 0.5–2 | 1 | 框、字体、按钮与文字整体缩放 |
| taskScale | 0.5–2 | 1 | 任务栏、行高、文字同比例缩放 |
| dialogOpacity | 0.1–1 | 1 | 框背景/阴影/边框，不影响文字或灯泡 |
| buttonOpacity | 0.1–1 | 1 | 按钮底色，不影响按钮文字 |
| taskOpacity | 0.1–1 | 0.9（Mac） | 任务栏底色，不影响名称/未读标记 |
| dialogGap | −80–200 pt | 0 | 相对原位置偏移；正值远离猪猪、负值靠近 |
| taskGap | 0–200 pt | 8 | 任务栏和稳定 idle 锚点之间的距离 |
| dialogColor | RGB 或未设置 | 原版渐变 | 未设置必须走默认渐变分支 |
| taskColor | RGB 或未设置 | Mac 系统窗口背景色 | Windows 默认应保留自己的原生任务栏样式 |
| dialogTextColor | RGB 或未设置 | 原版/背景对比色 | 标题与正文，不改文字 alpha |
| buttonTextColor | RGB 或未设置 | 原版主/次按钮文字色 | 不能用一个“白色默认值”覆盖所有按钮 |

预览勾选为界面临时状态，不属于恢复默认的持久化参数。UI 上的“不透明度”越高越实，Windows 文案也应保持一致。

## 坐标和渲染移植方案

保留 640×640 的原始逻辑画布与全局锚点 `(410,570)`；不要按每帧可见包围盒重新居中。对话框缩放基点 `(410,358)`。

建议分为三类变换：

- 宠物层：原图、睡眠分层、庆祝、小助手、更新灯泡，统一 `petScale`；小助手原相对比例仍保留。
- UI 层：对话框和任务栏分别应用自己的缩放；文字随框缩放，文字 alpha 为 1。
- 屏幕层：将逻辑坐标转换为系统/DPI 坐标。Windows 现有 `self.scale` 是 **DPI 比例**，必须另设 `petScale`，不能复用它。

Mac 对话框在宠物逻辑坐标中的变换为：

`x = 410 + (x0 − 410) × dialogScale/petScale`

`y = 358 − dialogGap/petScale + (y0 − 358) × dialogScale/petScale`

然后通过宠物视图的 `petScale` 映射屏幕。鼠标命中使用其逆变换。Windows 最后再乘 DPI 比例，禁止重复乘。拖动保持屏幕位移语义，缩放时固定猪猪脚部屏幕位置，避免跳位。

背景、按钮底色、文字分别画；框背景先合成为一个透明层再应用整体背景 alpha，避免阴影/填色/渐变叠加后错误变实。Windows 保持 straight RGBA 合成，缩放使用现有预乘转换路径，最终只做一次 BGRA 预乘。不要给整个 HWND 或最终合成图设置统一 alpha，否则字和猪猪一起变透明。

扩大绘制区域以容纳较大/向外移动的对话框；同步更新屏幕可见边界和权限/更新按钮 hit rect。动画灯泡边界属于宠物层，不得再次经过 dialogTransform。隐藏主尾巴由 68×petScale、小尾巴由 32×petScale 得到，屏外重叠量及小尾巴间距也同比例变化。

## 最新 Windows 代码落点与必须保留的修复

以下均核对了基准源码，非仅引用版本说明。`windows-preservation.json` 给出基准文件 SHA-256；此 PR 没有修改这些 Windows 文件。

| 文件/符号 | 已有行为，必须保留 | 新功能应如何接入 |
|---|---|---|
| `windows_pet.py:permission_surface` | `lru_cache(maxsize=4)` 缓存抗锯齿背景 | 缓存键加入颜色、大小、背景 alpha；勿每帧重建复杂蒙版 |
| `windows_pet.py:resize_alpha/scaled_frame_bytes` | 预乘缩放、透明边界 crop、与目标像素格对齐 | 保留优化；将宠物/对话框层变换后再走现有最终缩放路径 |
| `windows_pet.py:_render_current/_render_layered_window` | 只转换最终 DPI 尺寸一次 | 不能重新引入先转 640 BGRA 又丢弃的路径 |
| `pig_pet.py:load_ui_font` | `lru_cache(maxsize=32)` 字体缓存 | 字号随框缩放，继续缓存 |
| `windows_animation_timer.py:WindowAnimationTimer` | 固定 deadline；过期跳帧；single pending 通知 | 外观滑动不得重新建立抢占式高频队列 |
| `windows_pet.py:_wndproc(ANIMATION_MESSAGE)` | 在绘制前 sample 固定时刻，绘制完成 finally 才 acknowledge | 不可把 acknowledge 提前；这会回退 0.5.5 并挤占鼠标输入 |
| `windows_pet.py:_advance/compose`、`animation_clock.py` | 主猪/分层/子猪共用固定采样；保留各任务相位 | 调外观不能重置动画 epoch，不能改为回调到达时间采样 |
| `codex_observer.py:ObserverReader/_poll_background` | 单后台 reader；有界队列；UI 应用结果时对当前状态复核 | 滑条和预览不得在 UI 线程新增日志/SQLite 全量读取 |
| `family_store.py:children` | 隐藏 `interrupted` 且 `last_event < parent.turn_started` 的旧子任务 | 预览用独立样例，不能改真实 store 或绕过过滤 |
| `windows_pet.py:_composite_selector/_cursor_window_position` | 当前任务列表、DPI 命中与 hover 通道 | 任务尺寸/间距变化后重算行 rect、hover 通道、滚动范围 |
| `windows_pet.py:_mouse_up` 的 `selector_down` 分支 | 目前只有 `node.unread` 时 ShellExecute；成功后清蓝点及 `observer.opened` | 将 ShellExecute 移到所有任务共用路径；保留成功判断 `result > 32`；失败不清蓝点、不伪造已读；保留原任务选择逻辑 |
| `windows_pet.py:_composite_permission_bubble`、`update_notice.py:UpdateNotice.draw` | 权限与更新提示、灯泡、按钮处理 | 分离框层与宠物灯泡层，文字/底色分 alpha，不改权限决策或安装动作 |
| `windows_pet.py` 隐藏任务/庆祝固定规则 | 任务绑定隐藏直到完成、多子任务与提前唤回 | 仅变换显示与边界，不重置 hidden_family/celebration 状态 |
| `install.ps1`、hooks、`windows_update.py:install_transaction/recover_transaction` | 自启动偏好、权限/任务事件、签名/摘要、事务恢复与回滚 | 本轮不得重写/覆盖，升级后验证外观设置能保留 |

**跨端差异：** Mac 已读蓝点在 Codex 确认实际 read state 后消失；Windows 当前成功 ShellExecute 后记 `observer.opened`。本轮要求保留各端原机制并扩大跳转触发范围，不要因套用 Mac 文件回退 Windows 已完成逻辑。

## 文件和包的使用方式

1. Windows 机器先 `git fetch origin` 并核对自己的最新主分支。如果 main 又前进，以新的 Windows 修复为优先，比较本包基准后的增量。
2. 阅读本说明、`LESSONS.md`、`validation.json`；Mac 源码是行为参考，不能整目录覆盖 Windows。
3. ZIP 的 `changed-source/` 为候选改动文件；`changes.patch` 以本包基准生成，主要改变 Mac；`windows-baseline-reference/` 仅供对照，禁止当安装/覆盖源。
4. 逐项实现：持久设置 → 图层与坐标变换 → 命中/边界 → 字体颜色/alpha → 预览与 reset → 任意任务跳转 → 回归。复用 Windows 当前定时器/后台读取。
5. `assets/macos-resources/` 包含原始完整帧、动画清单、特效和尾巴源图。不要从录屏/GIF截图或重编码为 GIF 再导入。
6. 候选 Mac 应用供对照，Windows 不运行 `.app`。`SOURCE.json` 给出确切提交，`SHA256SUMS.txt` 校验包内文件，外部 `.sha256` 校验 ZIP。

## 素材保真

`animation-manifest.json` 原样保留，21 个动画，2167 帧，全部 640×640 RGBA PNG。全局身体锚点 x=410 / bottom=570；每帧 `duration_ms`、`visible_bounds` 和每动画 `loop_start` 均保留。缺失的 loop_start 按现有播放器默认为 0；不可重写原文件补值。`asset-inventory.json` 提供逐帧哈希与原有元数据。特效/尾巴等辅助图尺寸保持各自原尺寸。灯泡为程序绘制，不是缺失的 PNG，代码见 `UpdateNotice.swift:drawPetDecoration/drawBulb`。

## 验证与尚待完成的验收

Mac 本轮：arm64 与 x86_64 编译成功；在 Apple Silicon macOS 26.5 上运行原生 manifest 自检、完整 macOS CLI/hook 发布回归、外观像素/命中/保存/reset/预览测试、灯泡 50/100/200% 与四边尾巴缩放测试，以及四边隐藏任务原生回归共 48 项检查，均通过。Intel 仅编译，未实机运行。尝试运行 Windows 性能测试时，当前 macOS 缺少 winreg，因此没有取得 Windows 原生性能测试结果；见 windows-source-regression.log。

`native-playback.mp4` 是本次原生控制器与真实外观控件的录屏，来源 `tests/appearance-demo/main.swift`，独立 bundle ID 和临时状态，使用样例任务与既有 `--preview-update available` 合成更新通知（画面中的 0.5.0 是测试 fixture，不是真实可安装版本），没有点击安装。录屏标注平台、候选版本/构建和各场景。它不替代真实任务生命周期、Windows 点击响应或更新回滚验收。

Windows 逐项记录版本、构建、DPI、耗时/结果：

- [ ] 全部 21 个动画/分层正常，切任务不重置相位；50/100/200% 无漂移。
- [ ] 灯泡跟猪缩放；改对话框大小/距离/alpha 不改变灯泡。
- [ ] 睡眠身体/尾巴/Z、庆祝、小助手、四边大小尾巴同步缩放。
- [ ] 背景 alpha=10/25/100%、按钮独立 alpha、文字 alpha 始终 1；无黑边/双重预乘。
- [ ] 原版默认渐变恢复；reset 保留任意组合预览勾选及窗口位置。
- [ ] 字体随框缩放、长任务标题/长权限正文可读；按钮命中与显示一致。
- [ ] 真实位置预览随拖动/缩放/多屏 DPI 变化；不写真实任务、权限或 read-state。
- [ ] 所有状态任务点击均打开正确对话；成功/失败蓝点逻辑符合当前 Windows 机制。
- [ ] 任务栏滚动、多子猪、权限、更新气泡、拖动与隐藏恢复的组合场景。
- [ ] 125/150/200% DPI、多个显示器、最大框尺寸/间距屏边约束。
- [ ] 使用原性能测试、输入 canary 检查滑条/动画下鼠标点击不饥饿。
- [ ] 旧中断子任务过滤、后台读取、自启动偏好、权限发送、升级设置保留和失败回滚。

未完成上列 Windows 实机测试前，状态必须保持 **Windows 实机待验收**，不得宣称跨平台验收完成。
