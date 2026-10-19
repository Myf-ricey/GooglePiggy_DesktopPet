# macOS 0.5.3 → Windows 交接

## 基线与边界

Windows 基线：GitHub main 提交 938c40e1253511baeb8b3318ab6d3a75cbff876a，已发布 v0.5.1-windows。Mac 本次 v0.5.3-macos，构建 10。

请先合并／检查最新远端，保留 Windows 0.5.1 的更新器、压缩日志观察、状态恢复修复。不要把旧本机 codex_observer.py 或 Windows 文件整体覆盖回去。本交接只提供 Mac 实现参考、差异补丁和验收目标；Windows 原生验证与发布由 Windows 侧完成。

用户要求：版本号同步方案目前只讨论，不执行。本次不要顺便修改 Windows 版本号、旧标签或更新渠道。

## 1. 运行中强制隐藏持续到对应任务完成

Mac 参考：PetController.swift 的 beginEdgeHideIfNeeded、revealForActivityIfNeeded、refreshFamilyState、handleTailClick、presentUpdate。

- 在运行中隐藏时记录对应家庭／任务身份与隐藏时刻，不把工作 token 集合变化当作解除隐藏的条件。
- 读书与执行工具切换、压缩、中断／恢复、新增子任务、其他家庭开始或完成，都继续隐藏。
- 对应主任务成功且子任务全部结束后，解除隐藏；主任务先完成而子任务仍运行时继续等待。
- 完成时间必须晚于本次隐藏，不能用此前残留完成状态触发。
- 自动选择不能把隐藏任务换成另一户家庭；弹出后完整播放该任务的庆祝，之后恢复正常任务选择。
- 点尾巴立即解除隐藏，可在任务仍运行时使用。
- 自动更新提示不能越过运行中的隐藏约束；空闲时隐藏的原有唤出规则保留。

Windows 入口：windows_pet.py 的 hidden_tokens、activity_requires_visible_pet、_begin_edge_hide_if_needed；pig_pet.py 的 _reveal_for_activity_if_needed / _begin_edge_reveal；family_store.py 的 work_tokens 与任务选择。

四边分别验证：读书→执行工具、子任务开始、其他任务开始／完成、压缩开始／结束、中断／恢复、主任务先结束、子任务结束后弹出庆祝、庆祝结束切回其他工作任务；另实测尾巴点击。Mac 隔离原生脚本 tools/test_hidden_task_completion.py 可作为事件序列参考，不可直接当 Windows 验收结论。

## 2. Codex 建议安全检查过滤

已观察到的提示词开头（注意两次换行）：

```
You are an expert at upholding safety and compliance standards for Codex ambient suggestions.

```

Mac 同时要求 event=UserPromptSubmit、source=codex-hook、cwd=/、无显式或元数据父子关系、不是已注册正常线程。通过这些条件才记入 internalSessions，并清掉 SessionStart 占位；后续事件与重启回放不能让其复活。不按“线程 ……”名称过滤。

Windows 参考：codex_observer.py 的 INTERNAL_PROMPT_PREFIXES 与 ingest。先核对 Windows Hook 实际输出的 source/cwd；不要猜测 Windows 后台目录或把所有根目录视作后台。未确认的 Windows 形态应保持不过滤，避免误伤。

反例必须保留：已注册但无名称的正常线程、未注册的普通请求、真实子任务（显式 agent 或数据库父子关系）、普通项目目录中相同文字、引用而非开头出现、不同来源、相似但不完全匹配的提示词。

tests/suggestion-safety/observed-events.json 是脱敏事件模板；不含用户真实线程、对话、目录、数据库或密钥。main.swift 包含反例与迟到／重启测试。

## 验收与发布

先做 Windows 领域测试和原生窗口验证，确认原有更新、权限气泡、家庭切换、动画及休闲不回归。不得仅凭 Mac 测试声称 Windows 已通过。补丁 macos-0.5.3.patch 只用于理解 Mac 改动，不是 Windows 可直接应用的实现补丁。

版本号讨论：目前两端通过 -macos / -windows 标签独立筛选更新；数字按各自发布节奏递增。以后可约定共同目标版本（例如双方通过同一验收后都发布 0.6.0），继续保留平台后缀和独立构建号，补丁版本允许各自推进。不要重写已发布标签或为凑号声称两端功能已对齐。
