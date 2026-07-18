# GooglePiggy Desktop Pet v0.2.3

本版本继续完善原生 macOS 版的 Codex 权限交互，并包含此前测试周期发现的全部
修复。Windows 版源码、安装器、Hook 和构建流程保持不变。

## macOS 权限气泡修复

- 不再向用户显示内部工具名 `apply_patch`。
- 不再把 `*** Begin Patch`、`*** Update File` 等原始补丁协议直接放进气泡。
- 真实工具输入会转换成自然中文，完整说明准备执行的操作、目标文件和是否允许。
- 如果 `Bash:`、`apply_patch:` 只是完整中文理由前的重复标签，会移除该前缀。
- 如果权限 Hook 没有直接提供参数，会按 `session_id + turn_id + 工具类型` 从
  Codex 本地 session 记录恢复本次真实工具输入。
- session 恢复同时兼容 `{"cmd":"..."}` 与 `{cmd:"..."}` 两种 Codex 调用格式，
  并会恢复其中的中文 `justification`。
- 终端命令中嵌套的 `apply_patch` 会继续解析为具体文件动作和绝对路径；同一回合
  后续还有普通终端命令时，会优先匹配真正携带授权参数的调用。
- 文件补丁会逐项显示创建、修改、删除动作及对应完整路径；不会用文件数量代替目标。
- 常见终端操作会识别创建/删除文件、打开应用、调节屏幕亮度及系统设置；无法归类
  的命令会显示经过脱敏的具体命令。
- 用户主目录不再缩写为 `~`；绝对路径完整显示为 `/Users/用户名/...`。
- 相对文件路径会依据对应 Codex session 的任务工作目录还原为绝对路径。
- 长路径改为按字符多行换行，权限正文区域向上扩展，可显示多条完整路径。
- Bash/Shell 权限使用中文提示；若 Hook 与 session 都没有工具详情，猪猪不显示
  模糊授权，而将该次请求留给 Codex 原生授权界面处理。
- 拒绝操作时回传给 Codex 的说明改为中文。
- 加入真实 Codex session 回放，以及修改/创建/删除、打开应用、亮度调整、无引号
  JavaScript 字段、嵌套补丁和同回合多命令等黑盒回归测试。
- 覆盖安装时会可靠结束仍在运行的旧版进程，再启动磁盘上的新版本，避免升级后暂时
  看到旧界面。

## 已包含的早期 macOS 修复

- 取消右键菜单后猪猪不会消失或退出。
- 安装器、右键帮助和 README 明确提示首次进入 `/hooks` 信任 Hook。
- Codex 思考、完成和权限事件在完成信任后可正常联动。
- 权限文案支持多行显示。

## macOS 安装提醒

1. 运行发布包中的 `install.command`。
2. 在终端运行 `codex`，输入 `/hooks`。
3. 核对 GooglePiggy Hook 的安装路径，选择信任并继续。
4. 完全退出并重新打开 Codex 桌面版。

本地 Mac 包使用 ad-hoc 签名。若 macOS 首次拦截，请按住 Control 点击应用或安装
脚本，选择“打开”。正式面向普通用户发布时，建议使用 Developer ID 签名并完成
Apple 公证。

## 建议上传的 Release Assets

```text
GifPigDesktopPet-windows-x64.zip
GooglePiggy-macos-universal.zip
GooglePiggy-macos-universal.dmg
GooglePiggy-macos-arm64.zip
GooglePiggy-macos-arm64.dmg
GooglePiggy-macos-x64.zip
GooglePiggy-macos-x64.dmg
```
