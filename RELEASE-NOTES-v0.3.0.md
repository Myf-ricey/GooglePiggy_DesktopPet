# GooglePiggy Desktop Pet v0.3.0

这是一次 **仅面向 macOS** 的功能更新。Windows 版源码、安装器和现有发布包保持
`v0.2.3` 不变，Windows 对应实现会在后续版本单独更新。

## 空闲触边隐藏

- 猪猪处于空闲状态时，把它拖到屏幕左、右、上、下任一外边缘并松手，它会弹跳
  进入屏幕边缘，只露出一小截带描边的猪尾巴。
- 单击尾巴，猪猪会用独立的弹跳/拉伸动画回到桌面，并与边缘保留合适距离。
- 底边采用单独的回归位置，使跳回后的落点更贴近屏幕底部。
- 四个方向分别校准了尾巴旋转角度、裁切轮廓和屏外压入量；尾巴始终贴住显示器
  的物理边缘，不会悬浮在 Dock 或菜单栏的工作区边界。
- 多显示器之间的内部接缝不会触发隐藏，只有整个桌面的外边缘有效。

## 与工作状态联动

- 只有在 Codex 未工作、没有权限请求、也没有一次性动作时，猪猪才会进入隐藏。
- 如果 Codex 在猪猪隐藏期间开始思考、请求权限或完成任务，猪猪会自动跳回并显示
  对应状态。
- 隐藏和跳回不复用任务完成庆祝动作，避免错误出现烟花或完成反馈。

## 跨平台对接准备

- 平台无关的边缘判断、屏外位移、尾巴位置和跳回落点集中在
  `macos/Sources/GooglePiggy/EdgeHiding.swift`。
- `MACOS-PORTING.md` 记录了坐标系、可见像素边界、DPI、多显示器以及 Windows
  对接参数，后续 Windows 版无需照搬 AppKit 窗口代码。
- 新增四向视觉预览入口和黑盒回归测试，便于逐方向校准。

## 下载与安装

本次 Release 提供：

```text
GooglePiggy-macos-universal.zip
GooglePiggy-macos-universal.dmg
SHA256SUMS-v0.3.0.txt
```

Universal 包同时支持 Apple Silicon 与 Intel Mac。解压 ZIP 或打开 DMG 后运行
`install.command`；首次安装 Codex Hook 后，请在终端版 Codex 中输入 `/hooks`，
核对 GooglePiggy 路径并完成信任，然后重启 Codex 桌面版。

当前公开包使用 ad-hoc 签名，尚未经过 Apple 公证。若 macOS 首次拦截，请按住
Control 点击 `install.command` 或 `GooglePiggy.app`，选择“打开”。
