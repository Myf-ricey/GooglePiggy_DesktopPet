# GooglePiggy Windows 0.4.2

支持 Windows 10/11 x64，便携版无需 Python。本次实机验收环境是 Windows 11 24H2、单屏、150% DPI。

## 下载与安装

从 [Windows 0.4.2 Release](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/tag/v0.4.2-windows) 下载 `GooglePiggy-0.4.2-windows-x64.zip`，完整解压到准备长期保留的文件夹，例如 `D:\Apps\GooglePiggy`。不要只复制 EXE，也不要从压缩包内直接运行。

双击 `pig_pet.exe` 可以先试用。在解压目录打开 PowerShell，运行安装器即可启用完整联动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

安装器为当前用户创建桌面入口、设置登录自启动、注册十二项 Codex Hook，然后启动桌宠。它以当前解压目录作为安装位置，不会把程序搬到其他目录。已有 Hook 配置会备份，其他项目的 Hook 会保留。

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

任务列表排除应用生成“下一句建议”的已识别临时会话。子代理属于父任务家庭，不单列成新的家庭。缺少数据库与执行日志确认、且没有工具活动的启动记录，会在 45 秒后退出运行列表。

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

已进行状态／渲染／安装检查、便携 EXE 原生回放，以及多个真实聊天和三个子代理同时工作的用户测试。多显示器与其他物理 DPI 尚未实机验收。详细记录见 [本版验收](releases/windows-0.4.2/ACCEPTANCE.md)。
