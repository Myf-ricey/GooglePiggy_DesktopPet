# GooglePiggy Desktop Pet v0.3.2

这是一次跨平台尾巴隐藏更新：Windows 和 macOS 现在都支持完整的边缘隐藏、尾巴
点击跳回，以及可见的短暂进出动画。

## Windows / macOS 尾巴隐藏

- 空闲且处于 `responsive` 模式时，可从左、右、上、下四个物理外边缘隐藏。
- 主体会用约 0.48 秒的平滑过渡收进屏幕，只留下 68×68 的可点击尾巴窗口。
- 点击尾巴后，尾巴先收起，主体沿同一条平滑曲线滑回桌面。
- 两端都排除多显示器内部接缝，只在整个桌面的物理外边缘触发。
- Codex 开始工作、请求权限或完成任务时，隐藏中的猪猪会自动恢复显示。

## Mac 端动画完善

- macOS 原生 AppKit 端改用 60Hz 定时器逐帧移动窗口。
- Windows 和 macOS 共用 `smoothstep` 运动曲线，避免系统隐式动画造成节奏差异。
- 保留 19 帧的待机弹跳/拉伸揭示动画，进出过程可以清楚看到。

## 验证

本版本已通过：

```text
smoke_test=ok
macos_manifest_test=ok
macos_release_test=ok
macOS universal (arm64 + x86_64) build
```

完整 Mac 便携包：

```text
GooglePiggy-macos-universal-v0.3.2.zip
```

Windows 便携包：

```text
GifPigDesktopPet-windows-x64.zip
```
