# Codex Hook 兼容性基线与排查手册

本文用于在 Codex 官方 App 或 CLI 更新后快速判断 GooglePiggy 的 Hook 是否仍兼容。
它记录协议基线、测试入口和分层排查路径，不依赖某个用户的绝对目录。

## 已验证基线（2026-09-01）

| 项目 | 已验证值 |
| --- | --- |
| Codex/ChatGPT macOS App | `26.825.51511`（build `7377`，bundle `com.openai.codex`） |
| App 内置 Codex CLI | `0.151.0-alpha.7.2` |
| 同机终端 Homebrew Codex CLI | `0.144.5` |
| GooglePiggy hooks 总开关 | `~/.codex/config.toml` 中 `[features] hooks = true` |
| 用户 Hook 文件 | `~/.codex/hooks.json` |
| App 内置 Codex 可执行文件 | `/Applications/ChatGPT.app/Contents/Resources/codex` |
| GooglePiggy Hook | `~/Applications/GooglePiggy.app/Contents/MacOS/GooglePiggy --hook` |
| 权限等待时间 | `PermissionRequest = 600s`，其他状态事件 `10s` |

该环境安装了 `SessionStart`、`UserPromptSubmit`、`PreToolUse`、`PostToolUse`、
`Stop` 和 `PermissionRequest`。新写入或命令发生变化的 Hook 仍需在终端 Codex 的
`/hooks` 页面确认信任。

只读采集当前机器基线：

```zsh
python3 tools/codex_hook_snapshot.py
```

脚本只输出与兼容性有关的版本、事件、超时和非敏感配置；用户主目录会显示为 `~`。

## 当前官方 PermissionRequest 协议

官方 Hooks 文档：<https://learn.chatgpt.com/docs/hooks>

当前 `apply_patch` 的规范输入为：

```json
{
  "hook_event_name": "PermissionRequest",
  "tool_name": "apply_patch",
  "tool_input": {
    "command": "*** Begin Patch\n*** Update File: /path/to/file\n...\n*** End Patch"
  }
}
```

允许必须返回：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": { "behavior": "allow" }
  }
}
```

拒绝使用同一层级的 `behavior: "deny"`，并可在 `decision.message` 中给出原因。
若 GooglePiggy 无法取得足够详情，应返回 `{}`，让 Codex 使用原生权限窗口。

## 2026-09-01 兼容性回退

症状：修改沙盒外文件时，Codex 原生权限卡出现，猪猪仍处于工作动画，没有显示
权限气泡。

根因：`PermissionRequest` 已正常触发，但当前 `apply_patch` 把补丁放在
`tool_input.command`。旧解析器只检查 `input`、`patch`、`patch_text`、`text` 和
`content`，因此记录 `permission-details-unavailable` 并返回 `{}`。

修复：

- 优先解析 `tool_input.command`，同时保留旧字段兼容；
- 当直接详情缺失时，可从代码模式 session 记录中还原带 `\\n` 转义的补丁；
- `tools/test_macos_release.py` 固化当前真实载荷和代码模式回退两项测试。

## 更新后快速定位

1. 运行 `python3 tools/codex_hook_snapshot.py`，保存更新前后输出并比较 App 内置
   CLI、终端 CLI、`hooks = true`、事件清单、命令路径和超时。
2. 查看 `~/Library/Application Support/GifPigDesktopPet/codex-hook-events.jsonl`：
   没有事件通常是 Hook 未安装、未信任或未匹配；有 `ignored=true` 则是
   GooglePiggy 收到了事件但解析或运行条件不满足。
3. 查看 `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`，找到同一回合的
   `custom_tool_call`，确认真实工具名与输入结构。
4. 查看 `~/Library/Logs/com.openai.codex/YYYY/MM/DD/`：若出现
   `item/fileChange/requestApproval`，说明 Codex 已进入原生文件审批流程。
5. 将真实输入加入 `tools/test_macos_release.py`，先让旧实现失败，再修改解析器。
6. 构建后运行完整黑盒测试，并分别实测一次猪猪“允许”和“拒绝”。

判断顺序固定为：事件是否触发 → 输入是否可解析 → 猪猪是否存活 → 返回 JSON 是否
符合官方协议 → Codex 是否接受决定。这样可把“Hook 没运行”和“Hook 运行后主动放弃
接管”分开，避免只看界面猜原因。
