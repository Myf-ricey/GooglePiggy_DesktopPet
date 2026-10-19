# Windows 0.5.3 验收（2026-10-19）

版本 0.5.3-windows，构建 20261019.1-hidden-family。基线 GitHub main a61b1afe188dd782dc6b6e57b19c9923da5d5d43，保留 macOS 0.5.3 及工作流。

- PASS：56 项单元／领域／渲染／更新回归；先复现隐藏提前唤出、安全检查漏过滤、系统禁用状态显示错误及压缩后直接完成丢失，再修复。
- PASS：PowerShell 5.1 Hook SelfTest。
- PASS：12 项打包 EXE 原生回放：并发 Hook、家庭选择、四边、权限独立响应、休闲与退出。
- PASS：5 项专项原生验收：四边各覆盖工具、子任务、其他家庭、压缩、中断恢复、更新提示、主任务先完成、子任务最后结束、完整庆祝、恢复其他工作；尾巴唤出同一处理函数。
- PASS：7 项打包观察器验收：压缩日志、大日志、元数据定向查询、实时安全过滤正反例和重启回放。
- PASS：5 项隔离真实 EXE 更新验收，使用现有 0.5.1 副本升级到 0.5.3；保留额外设置、权限推迟重启、完整备份；损坏下一版可执行文件后恢复 0.5.3 并重启。
- PASS：首次运行默认开启、保存的关闭偏好、Windows 禁用标记、旧版本无 Run 项的迁移保留均有隔离回归；测试进程不触碰真实自启动。

原生环境：Windows 11 24H2、150% DPI、单屏。100/125/200% DPI 与负坐标沿用离线几何测试，多物理显示器、真实注销／重启及断电恢复未实测。尾巴通过与点击相同的原生处理方法验收，未注入鼠标输入。

本机旧版 EXE 和 Codex hooks.json 保持原哈希；所有新版程序在隔离目录运行。当前用户 Run 启动项存在，目标旧版 EXE 存在，无 StartupApproved 禁用标记；初查未发现运行进程或错误日志，无法仅据这些事实判定此前未运行的原因。

源码回归：`py -3 -m unittest tools.test_handoff_053 tools.test_windows_port tools.test_windows_update tools.test_internal_memory tools.test_compressed_rollout tools.test_state_audit -q`。

原生专项：`py -3 -m tools.test_hidden_053_runtime --exe`（可用 GOOGLEPIGGY_TEST_EXE 指定独立候选程序）。更新验收：`py -3 tools/test_windows_update_runtime.py <新目录> <0.5.1目录>`，仅复制两者后操作副本。
