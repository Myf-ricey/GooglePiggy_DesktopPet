# GooglePiggy Desktop Pet v0.3.1

这是 Windows 端对 macOS `v0.3.0` 边缘隐藏功能的配套实现。macOS 原生运行时和
现有功能保持不变。

## Windows 边缘隐藏

- 猪猪处于 `responsive` 空闲模式时，可从左、右、上、下四个物理外边缘隐藏。
- 隐藏时主窗口平滑移出屏幕，只保留 68×68 的独立尾巴窗口。
- 单击尾巴会播放 19 帧揭示动画，猪猪回到桌面。
- 多显示器内部接缝不会触发隐藏。
- Codex 开始工作、请求权限或完成任务时，隐藏中的猪猪会自动恢复显示。
- 拖拽、右键菜单和原有状态联动保持兼容。

## 验证

本版本已通过：

```text
runtime_edge_smoke=ok
smoke_test=ok
PyInstaller build completed
```

Windows 便携包：

```text
releases/GifPigDesktopPet-windows-x64.zip
```
