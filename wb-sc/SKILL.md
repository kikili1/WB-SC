---
name: wb-sc
description: 在 Windows 或 macOS 查询、规划和修改 WorkBuddy 桌面端或 CodeBuddy CLI 快捷键，检查冲突并排查语音输入键、全局唤醒热键和 keybindings.json。遥控器实体键、Dongle 和状态 Hook 使用 dongle-control。
metadata:
  agent_created: true
---

# WB-SC

先识别执行主机的操作系统，选择对应入口；不要把 Windows 路径或 PowerShell 命令套到 macOS。

## Windows

- 使用 Python 3.8+，运行 `python scripts/wbsc.py detect`；桌面键位使用 Windows 默认值和冲突规则。
- 快捷键功能无需第三方 Python 依赖；Windows HID 后端保持原生实现。

## macOS

- 目标 macOS 12+（Intel / Apple Silicon）、Python 3.10+；运行 `python3 scripts/wbsc.py detect`。
- 使用 Mac 默认值和冲突规则，`Cmd/Command/Meta` 表示 ⌘，`Option/Alt` 表示 ⌥。CLI 的 Ctrl 不转换为 Cmd。
- 快捷键功能无需 HIDAPI。Dongle 与 Hook 按 [macOS 安装与验收](../dongle-control/references/macos.md) 操作。

## 两平台共用操作

- **定位桌面端或 CLI** → 用 `scripts/wbsc.py detect`，按 [快捷键说明](references/shortcuts.md) 选择配置入口。
- **查询和检测冲突** → 用 `list` 或 `check`。
- **修改桌面快捷键** → 先用 `plan`，按 [快捷键说明](references/shortcuts.md) 的桌面端流程执行。
- **修改 CLI 快捷键** → 用 `apply-cli`，参数见 [快捷键说明](references/shortcuts.md)。
- **控制 Dongle、改键、重置遥控器配置或管理状态 Hook** → 读 [dongle-control](../dongle-control/SKILL.md)，安装与修复按其链接的安装流程执行。
