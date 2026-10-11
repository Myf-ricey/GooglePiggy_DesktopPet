# GooglePiggy Windows v0.4.2

Windows 桌宠同步 macOS 0.4 的多任务家庭、动画与休闲互动，并包含实际测试中发现的问题修复。

## 新功能与调整

- 直接使用 21 段、2167 帧原始 RGBA 动画；阅读、八种整理、跳跃庆祝保持各任务的动画进度。
- 多个聊天分别显示家庭，子代理显示为最多三只小猪与 `+N`；支持家庭切换、未读提示和全家触边隐藏。
- 新增睡眠、独立尾巴／ZZZ、偷吃和唤醒互动。
- 十二项 Codex Hook、并发权限请求隔离；权限气泡只保留“允许一次”“拒绝”，长内容可滚动。
- 修复无后续记录的启动事件长期留在任务列表的问题。
- 修复 Codex 自动生成“下一句建议”的临时会话被显示成额外任务编号的问题。
- 修复底边展开时家庭显示不完整的问题。

## 下载

- `GooglePiggy-0.4.2-windows-x64.zip`：Windows 10/11 x64 便携版，无需 Python。
- `GooglePiggy-0.4.2-source.zip`：本版完整源码与共享素材。
- `SHA256SUMS.txt`：附件校验值；其中 EXE 校验项对应便携包内的 `pig_pet.exe`。
- `release-manifest.json`：源码提交及附件版本信息。

完整解压后双击 `pig_pet.exe`。需要 Codex 联动、桌面入口和自启动时，在解压目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

升级前先退出旧版。按安装器提示在 Codex `/hooks` 中审核十二项 Hook，然后新建聊天或重启客户端。安装目录应长期保留。[完整安装说明](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/blob/main/README-WINDOWS.md)

## 验证

19 项状态／渲染／安装检查通过；实际临时会话事件回放确认过滤有效，三个子代理父子关系正确。便携程序及最终解压包均进行 12 项原生回放检查。用户已同时布置四个真实聊天，其中一个包含三个并行子代理，并反馈其余交互正常。

实机环境：Windows 11 24H2、x64、单屏、150% DPI。多屏及其他物理 DPI 尚未实机验收，程序未签名。

macOS 保持 [v0.4.0-macos](https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/tag/v0.4.0-macos)；本次是 Windows 专属发行。
