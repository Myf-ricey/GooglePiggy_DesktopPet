# GooglePiggy Windows 0.4.2 实现与验收

本版以 2026-10-09 Mac handoff 和 GitHub main `ba11094445482de445452bbe57d219e0e6c6cf54` 为功能／素材基线。旧 Windows 工作区的修改保留。所有生产动画直接来自原 RGBA PNG，不重绘、不从 GIF 抠帧。

## 运行

解压 `GooglePiggy-0.4.2-windows-x64.zip`，运行 `pig_pet.exe`。无需 Python。
可先直接试用；正式安装执行同目录 `install.ps1`，注册自启动、桌面入口和十二项 Hook。
首次 Hook 信任须在 Codex 自己的 `/hooks` 流程完成。已有聊天可能沿用旧 Hook 快照，需要新聊天或重启客户端。

正式菜单只含状态互动、休息模式、自启动、首次授权说明、退出。
权限气泡支持滚动，仅显示允许／拒绝；决定只回传当前 request_id。同一 actor 的并发请求依次显示。
桌宠只读 Codex 私有数据库与已读状态文件，不修改它们。未识别账号／主机 schema 时保留本地蓝点。

## 验证

```powershell
py -3 tools/test_windows_port.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File hooks/codex-pig-hook.ps1 -SelfTest
py -3 tools/test_windows_runtime.py --exe
```

`test_windows_port.py` 覆盖状态、时钟、休闲、并发原子写入、只读元数据、未知未读 schema、中文安装路径与保留其他 Hook。
原生回放以独立状态目录运行真实 layered window。涵盖十二个并发 Hook、切任务续读、四边家庭隐藏、新回合唤回、暂停／压缩屏障、不同及相同 actor 的并发权限、睡眠尾巴及退出。
开发回放仅在显式 `--qa-window --no-codex-observer` 下启用；生产启动不读取 QA 命令。

本机实测为 Windows 11、150% DPI、单显示器。100/125/200% DPI、负坐标及内部接缝有几何／缩放代码覆盖，但没有对应物理硬件实测。真实 Codex UI 的首次信任、跨账户／远程线程与发布后的 CI 仍属于外部验收；不把合成事件当这些项目已通过。
完整验收矩阵与证据位于 `releases/windows-0.4.2/ACCEPTANCE.md`，源码及便携包均附带。

## 发布与回滚

本版标签为 `v0.4.2-windows`，源码在 GitHub main 的 Mac 基线上应用 Windows 修改，保留 Mac 源码与构建脚本。本次保留远端原有工作流，提交使用 `[skip ci]` 避免 Windows 标签触发 Mac 发行，随后单独手动运行 Windows 构建。

发行包不包含用户 Hook 配置、账户资料、真实事件、QA 状态或开发 cache。源码提交及附件 SHA256 见 Release 的 `release-manifest.json` 和 `SHA256SUMS.txt`。

升级先退出旧 GUI，保留旧程序和 Hook 配置备份，再运行新版安装器。具体安装、授权与卸载步骤见 [README-WINDOWS.md](README-WINDOWS.md)。

## 0.4.2 实机修复

无数据库／日志确认且缺少后续活动的启动事件 45 秒后退出运行状态；已识别的应用自动建议会话不进入任务列表。三个真实子代理仍归属父任务。权限界面移除“全文”入口，保留滚动与允许／拒绝。
