---
name: dongle-control
description: 通过 WB-SC 向 USB Dongle 转发遥控器改键、整机配置重置、单键恢复、点灯和查询命令，或首次安装、修复、卸载 WorkBuddy 状态 Hook。不适用于桌面快捷键配置、固件升级或硬件调试。
---

# dongle-control

使用同级 `wb-sc/scripts/wbsc.py`。命令和参数见 [协议与调用](references/protocol.md)。

当前面向 HM-AItest-1（W306A）遥控器与接收器一对一使用。安装成功后必须回复型号、改键操作、恢复出厂操作和状态灯说明，格式见 [安装流程](references/hook-events.md)。

- **改遥控器实体键** → `key list` 查款式和位置，`key push --json` 预览或写入。明确请求写入时才加 `--yes`。按键名写入前确认款式。
- **恢复出厂／弃用改键 map** → `remote reset --json` 预览；用户明确要求重置时用 `remote reset --json --yes`。弃用全部主机覆盖并重启；仅 `outcome=discarded` 才确认弃用状态已保存。影响范围和回执见 [协议与调用](references/protocol.md)。
- **恢复单个按键** → `key push --name <键名> --restore --json` 预览，用户明确要求恢复该键时加 `--yes`，仅 `outcome=saved` 才算恢复成功。这会写回已确认款式表中的出厂值；不是整机恢复出厂。未指定重置对象时先确认范围。
- **点灯、枚举或查询** → `led send`、`led list` 或 `remote info`。
- **首次安装或修复 Hook** → 按 [安装流程](references/hook-events.md) 执行，包含提前授权、安装验收和简短回复。排障用 `remote doctor`，卸载用 `remote uninstall --yes`。
- **核对支持的事件、安装生效或联调** → 读 [WorkBuddy Hook 事件](references/hook-events.md)。

## 改键后的回复

- 默认只用一句话说明按键和改后的功能，例如：“已将 S1 改为 Ctrl+D。”多个按键可合并为一句，或每键一行。
- 隐藏命令、协议、键码、参数、JSON、回执字段、文件路径及执行过程；仅在用户明确追问时展开技术细节。
- 仍按真实回执判断结果；失败或结果未知时只简短说明原因及必要的下一步，不将发送成功当作保存成功。
- 不追加总结、测试清单、通用提醒或无关说明。
