# macOS 移植审计与等功能设计

## 结论

Windows 版不能直接在 macOS 运行，原因不是素材或 Python 版本，而是窗口系统、
输入、自启动、进程互斥、Codex hook 和发布格式全部绑定 Windows。Mac 版因此
采用原生 Swift/AppKit 运行时，同时复用原版动画处理算法与素材，避免交互或画质
降级。

## 不兼容点与对应修改

| Windows 实现 | macOS 不兼容原因 | Mac 版实现 |
| --- | --- | --- |
| `ctypes.windll.user32/gdi32`、`UpdateLayeredWindow` | macOS 没有 Win32 layered window、HDC、DIB | 透明无边框 `NSPanel` + AppKit alpha 合成 |
| `WS_EX_TOPMOST`、`WS_EX_TOOLWINDOW` | Windows 专用窗口扩展样式 | floating window level、Accessory app、跨 Spaces/全屏辅助显示 |
| Win32 消息循环与 `WM_*` 鼠标消息 | Cocoa 使用事件分发和 RunLoop | `NSView` 鼠标事件 + `Timer` 驱动逐帧动画 |
| `SetCapture/ReleaseCapture` | macOS 没有 Win32 mouse capture | AppKit drag tracking + 全局屏幕坐标移动窗口 |
| GDI BGRA 预乘 alpha | AppKit 图像表示不同 | 预导出 RGBA PNG 帧，AppKit 保留逐像素透明度 |
| Win32 `TrackPopupMenu` | 菜单 API 不存在 | 原生 `NSMenu`，保留全部预览、自启动、退出项 |
| 注册表 `HKCU\\...\\Run` | macOS 没有注册表 | 当前用户 LaunchAgent，右键菜单和安装器均可切换 |
| `CreateMutexW` | Win32 内核 mutex 不存在 | 状态目录文件锁 `flock`，仍只允许一个实例 |
| `%LOCALAPPDATA%` | 环境变量和目录约定不同 | `~/Library/Application Support/GifPigDesktopPet/` |
| PowerShell Codex hook | macOS 默认无 Windows PowerShell，路径语法不同 | App 自身的原生 CLI `GooglePiggy --hook` |
| PowerShell 后台完成 watcher | `Start-Process powershell.exe` 不存在 | 原生子进程扫描同一 Codex session JSONL |
| PowerShell 权限请求阻塞桥 | Shell/编码/进程检测逻辑不兼容 | Foundation JSON + POSIX PID 检测 + 原子文件响应 |
| `.cmd/.ps1` 安装与快捷方式 | Finder/LaunchServices 使用不同发布模型 | `.app`、`install.command`、`uninstall.command` |
| PyInstaller Windows portable folder | PE 可执行文件不能在 Mac 运行 | 原生 Mach-O `.app`，ZIP + DMG，运行时零 Python 依赖 |
| Windows 字体目录 | `C:\\Windows\\Fonts` 不存在 | AppKit 系统字体与中文 fallback |
| Windows x64 单架构 workflow | Apple Silicon 与 Intel 二进制不同 | GitHub Actions 分别构建 arm64 与 x64 |

## 功能对等矩阵

| 功能 | Windows | macOS |
| --- | --- | --- |
| 呼吸待机 | 有 | 同一 49 帧生成规则 |
| 点击躺平 | 有 | 有 |
| 拖动左拱 | 有 | 有 |
| 空闲触边隐藏、点尾跳回 | 待对接 | 有，支持四个桌面外边缘 |
| Codex thinking 追胡萝卜 | 有 | 有 |
| Codex success 跳跃 | 有 | 同一 61 帧筛选规则 |
| 火花与烟花 | 有 | 有，同位置/时长/淡入淡出公式 |
| 权限疑问猪 | 有 | 有 |
| 允许/拒绝回传 | 有 | 有，协议结构一致 |
| 长任务完成 fallback watcher | 有 | 有 |
| thinking/permission 过期恢复 | 有 | 有，阈值一致 |
| 右键七种模式 | 有 | 有 |
| 开机自启动 | 注册表 | LaunchAgent |
| 单实例 | Win32 mutex | POSIX 文件锁 |
| 置顶/透明/无 Dock 图标 | 有 | 有 |
| 不要求用户安装 Python | 有 | 有 |
| 自动构建发布包 | Windows ZIP | Mac arm64/x64 ZIP + DMG |

## 保持一致的动画资产

`tools/export_macos_assets.py` 在构建时加载原 `pig_pet.py` 的动画处理管线：

- 背景去除和透明边缘清理；
- 猪身体尺寸归一；
- 固定 `BODY_ANCHOR_X=410`、`BODY_ANCHOR_BOTTOM=570`；
- 左拱速度、跳跃帧选择、呼吸形变；
- 现有 sparkle/firework 素材。

因此 Mac 版不是重新解释 GIF，而是消费与 Windows 版同源的标准化帧。

## 触边隐藏的 Windows 对接契约

macOS 把平台无关规则集中在 `EdgeHiding.swift`，`PetController.swift` 只负责编排
AppKit 窗口和动画。Windows 版可直接按以下契约接入，而不需要照搬 `NSPanel`：

1. 仅当 `mode == "responsive"`、桥接状态为 `idle`、没有权限请求、没有一次性
   动画时允许隐藏。`thinking`、权限请求和完成特效都要求猪猪保持可见；若它们在
   隐藏期间到达，应自动触发跳出。
2. `animation-manifest.json` 每帧的 `visible_bounds` 是
   `[left, top, right, bottom]`，坐标原点在 640×640 动画窗口左上角。边缘碰撞必须
   使用这个非透明像素框，不能使用整个透明窗口。
3. `touchedDesktopEdge`、`offscreenDelta`、`revealedDelta` 和
   `tailWindowFrame` 是纯几何参考实现。输入转换到“屏幕坐标、Y 轴向上”后，
   Win32 端只需把结果交给 `SetWindowPos` 或自己的插值动画。
4. 隐藏碰撞、完全移出和尾巴位置使用显示器物理 `frame`；完整猪猪跳回时使用避开
   Dock/菜单栏的 `visibleFrame`。不能把后者当物理边缘，否则底部尾巴会悬浮。
5. 当前参数为：触边容差 10 pt、完全入边额外距离 16 pt、跳回后可见内容距边缘
   28 pt、尾巴点击窗 68×68 pt、向物理屏幕外压入 30 pt、位移动画 0.48 秒。
   Windows 在 DPI 缩放后使用对应逻辑像素，并允许尾巴点击窗有同样的屏外部分。
   从底边跳回时是例外：在标准安全位置基础上，再向下移动 1 个当前猪猪的非透明
   像素高度。不得使用 640×640 透明宿主窗口的高度。
6. 四向尾巴由 `tools/export_macos_assets.py` 从 `flat` 首帧自动裁切，输出到
   `edge-tail/{left,right,top,bottom}.png`；Windows 可以直接复用导出文件或同一
   裁切函数。右边缘姿态以现场反馈为准，相对旧姿态逆时针旋转 90°；四向素材按
   非透明像素框贴边，透明画布不参与锚定。导出器保留更大的尾巴与臀部区域，先将
   两条裁切侧生成带深色描边的圆弧，再按方向旋转：左边缘顺时针 50°，右、上、下边缘
   顺时针 55°。右、上、下仍由同一姿态以 90° 步进派生；左边缘则从未倾斜的左向
   基准独立生成。四向素材在旋转后原本各露出约 47 pt，向各自物理屏幕边缘外移动
   约 24 pt，因此统一使用 30 pt 总压入量，最终露出深度约 23 pt。
7. 跳出不复用任务完成的 `jump` 庆祝动画。`edge_reveal` 从待机首帧生成一次
   19 帧的上下弹跳/纵向拉伸，AppKit 使用 PNG 序列，同时输出
   `animations/edge-reveal.gif` 供预览和跨平台对接。
8. 多显示器内侧接缝不算桌面外边缘。macOS 用相邻屏幕探针排除接缝；Win32 可用
   `EnumDisplayMonitors` 做同样判断。

## 首轮真实使用回归

| 用户现场问题 | 根因 | 版本处理 |
| --- | --- | --- |
| 取消右键菜单后猪猪消失 | 非激活透明面板缺少菜单结束恢复，且旧窗口策略允许最后窗口关闭后退出 | 禁止因最后窗口关闭自动退出；菜单结束后强制恢复窗口并刷新心跳 |
| 只有待机/点击/拖动，Codex 思考和完成不联动 | Codex 对新用户 Hook 默认为 `untrusted`，重启不会自动信任 | 安装器、右键帮助和 README 明确引导用户进入 `/hooks` 审核；发布测试检查提示存在 |
| 权限说明第一行后过早省略 | 正文错误使用单行/尾部省略布局，长路径也不适合按词换行 | `0.2.3` 改为按字符多行布局，取消最后一行自动省略，并以真实中文长路径做回归测试 |
| 权限说明只有工具名、没有目标 | macOS PermissionRequest 可能不直接附带 `tool_input` | 按 session、turn 和工具类型恢复真实调用；显示具体动作和绝对路径，恢复失败时不弹出模糊授权 |
| 权限气泡显示 `apply_patch`、英文补丁协议且路径被截断 | Hook 有时不直接携带工具参数；旧实现又把内部补丁载荷或空泛兜底当作面向用户的说明 | `0.2.3` 按任务、回合和工具类型从本地 session 恢复真实参数，解析创建/修改/删除路径及常见系统命令，并扩展详细说明区域 |
| 授权只在 Codex 内显示，猪猪没有疑问动画 | 真实 session 使用 `{cmd:"..."}`，旧恢复器只匹配 `{"cmd":"..."}`，解析失败后主动交回 Codex | 同时解析两种字段格式、中文理由和终端内嵌补丁，并优先选择同回合中真正携带授权参数的调用 |

## 发布与安全边界

- 默认构建为 ad-hoc 签名，适合本地验证和开源产物。
- 面向普通用户发布时，建议 Developer ID 签名并 notarize，消除 Gatekeeper
  首次 Control-click 打开步骤。
- hook 只读取 Codex 提供的事件及同一任务的本地 session 工具调用/完成标记；
  权限摘要继续做 token/secret/password 脱敏。
- Codex 会对用户级 Hook 执行独立的信任校验。安装器只登记 Hook，不绕过该
  安全边界；用户需在终端版 Codex 的 `/hooks` 页面选择
  `Trust all and continue`，随后桌面版 Codex 才会执行联动。
- 安装和卸载 hooks 前都会备份 `~/.codex/hooks.json`，并保留其他项目 hooks。
