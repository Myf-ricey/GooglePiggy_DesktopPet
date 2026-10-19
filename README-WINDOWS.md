# GooglePiggy Windows 0.5.5

支持 Windows 10/11 x64，便携版无需 Python。本次实机验收环境是 Windows 11 24H2、单屏、150% DPI。

## 下载与安装

从 [Windows 0.5.5 Release](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/tag/v0.5.5-windows) 下载 `GooglePiggy-0.5.5-windows-x64.zip`。完整解压到准备长期保留的文件夹，例如 `D:\Apps\GooglePiggy`。不要只复制 EXE，也不要从压缩包内直接运行。

首次双击 `pig_pet.exe` 会默认设置当前用户登录自启动；右键菜单可以关闭，以后启动、安装和更新保留该选择。开发／隔离测试不会设置自启动。在解压目录打开 PowerShell，运行安装器即可启用完整联动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

安装器为当前用户创建桌面入口、按保存的偏好设置登录自启动、注册十二项 Codex Hook，然后启动桌宠。它以当前解压目录作为安装位置，不会把程序搬到其他目录。已有 Hook 配置会备份，其他项目的 Hook 会保留。

可选参数可以组合：

```powershell
# 不设置开机自启动
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -NoAutostart
# 仅安装桌宠，不注册 Codex Hook
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -NoCodexHooks
# 注册 Hook，但不创建桌面入口、不自启动，也不立即启动程序
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -NoAutostart -NoDesktopShortcut -NoStart
```

## 首次连接 Codex

1. 按安装器打印的完整路径启动 Codex CLI；如果 `codex` 已加入 PATH，可直接运行 `codex`。
2. 输入 `/hooks`，审核并信任十二项 GooglePiggy Hook。只有列表中全部 Hook 都可信时才使用“Trust all”。
3. 新建聊天或完整重启 Codex Desktop，让任务使用新的 Hook 配置。只重启客户端不会代替信任审核。

每次升级后如果 Hook 内容或路径发生变化，需要再次完成审核。桌宠不会代替你修改 Codex 信任数据库。

## 使用

| 操作或状态 | 表现 |
| --- | --- |
| 新消息进入思考 | 大猪拿书阅读 |
| 执行工具 | 追胡萝卜 |
| 压缩上下文 | 随机整理物品 |
| 任务完成 | 跳跃庆祝 |
| 中断／权限请求 | 疑问动作；真实权限请求有确认气泡 |
| 鼠标移到大猪上 | 展开任务列表；点击任务切换家庭 |
| 并行子代理 | 在父任务家庭下显示小猪，最多三只，超过显示 `+N` |
| 拖到屏幕外边缘 | 全家藏起；点击尾巴展开 |
| 空闲／右键休息模式 | 偷吃或睡眠；点击睡猪可能摆尾或唤醒 |

权限气泡只提供“允许一次”和“拒绝”。长内容用鼠标滚轮阅读，读到末尾后才能允许；每次决定只针对当前请求。未通过 `PermissionRequest` Hook 发出的授权提示仍需在 Codex 中处理。

任务列表过滤已识别的下一句建议、首页推荐、Claudian 标题生成和专用目录中的 Memory Writing Agent Phase 2。普通聊天和真实子代理保留；子代理归属父任务。缺少数据库与执行日志确认、且没有工具活动的启动记录，会在 45 秒后退出运行列表。程序同时读取 `.jsonl` 与 `.jsonl.zst` 生命周期记录，并对实际活动线程定向查找元数据，避免旧子任务残留；正常长任务不会因静默被统一超时结束。

## 检查更新与一键安装

每次启动后台检查一次 Windows 正式版本；右键“检查更新…”可手动检查。有新版时显示暖黄色灯泡和更新气泡，支持“稍后再说”“更新”、下载进度、取消下载和失败重试。权限气泡优先，拖动或处理权限时延后重启。

只从固定 GitHub 仓库获取 `v*-windows` 正式版本与对应 x64 ZIP。下载后核验 GitHub 附件 SHA-256、包内文件清单和版本，再由独立辅助程序备份整个安装目录、原路径替换和重启。新版启动失败时恢复旧目录。状态数据、其他配置文件、自启动和 Hook 注册路径保留，更新器不重写 Codex 配置。备份位于安装目录同级的 `.backup-…` 目录。

Windows 校验依赖 HTTPS GitHub 发布元数据和 SHA-256；尚未加入发布者独立数字签名。缺少 GitHub 摘要或 Windows 更新清单的包会拒绝自动安装。0.4.2 用户需要先手动安装一次 0.5.5，才能获得后续版本的更新入口。

## 升级与卸载

1. 右键退出旧桌宠，保留旧程序目录作为回滚备份。
2. 将新版解压到固定位置，运行新版 `install.ps1`，让快捷方式及 Hook 指向新版目录。
3. 完成 Hook 审核并新建聊天，确认新版能响应后再处理旧目录。

卸载当前目录注册的入口、Hook 与自启动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
```

卸载脚本不删除程序目录。运行状态保存在 `%LOCALAPPDATA%\GifPigDesktopPet\`；程序只读 Codex 的线程元数据与生命周期日志，以核对标题、父子关系、完成和已读状态，不写这些 Codex 数据。

## 排查

- **桌宠可见但不联动**：确认已运行安装器、完成 `/hooks` 审核，并用新聊天测试；检查安装目录是否移动。
- **找不到 Codex 命令**：使用安装器输出的桌面版内置 CLI 完整路径。
- **完成后仍有任务行**：有未读结果时会保留任务行；点开对应任务后再观察。
- **权限气泡没有出现**：先查看 Codex 是否发出了真实 `PermissionRequest`；部分确认只能在客户端处理。
- **下载被系统拦截**：本版未签名，可对照 Release 的 `SHA256SUMS.txt` 核验下载文件；只运行你确认来源的程序。

## 验收范围

本轮测试与证据见 [0.5.5 验收](releases/windows-0.5.5/ACCEPTANCE.md)。本机为 Windows 11、150% DPI、单屏。100/125/200% DPI 与负坐标采用离线渲染／几何测试，其他物理显示器尚未实测。

运行中拖到边缘隐藏时，家庭保持不变，直到主任务成功且子任务全部结束才弹出并完整庆祝；点击尾巴可提前唤出。更新提示不打断该隐藏状态。Windows 0.5.1 用户可直接一键升级到 0.5.5。
