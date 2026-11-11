---
name: wb-sc
description: 查询、规划和修改 WorkBuddy 桌面端或 CodeBuddy CLI 快捷键，检查冲突并排查语音输入键、全局唤醒热键和 keybindings.json。遥控器实体键、Dongle 和状态 Hook 使用 dongle-control。
metadata:
  agent_created: true
---

# WB-SC

- **定位桌面端或 CLI** → 用 `scripts/wbsc.py detect`，按 [快捷键说明](references/shortcuts.md) 选择配置入口。
- **查询和检测冲突** → 用 `list` 或 `check`。
- **修改桌面快捷键** → 先用 `plan`，按 [快捷键说明](references/shortcuts.md) 的桌面端流程执行。
- **修改 CLI 快捷键** → 用 `apply-cli`，参数见 [快捷键说明](references/shortcuts.md)。
- **控制 Dongle、改键、重置遥控器配置或管理状态 Hook** → 读 [dongle-control](../dongle-control/SKILL.md)，安装与修复按其链接的安装流程执行。
