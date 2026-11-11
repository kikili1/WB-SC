---
name: dongle-control
description: 通过 WB-SC 向 USB Dongle 转发遥控器改键、点灯和查询命令，或首次安装、修复、卸载 WorkBuddy 状态 Hook。不适用于桌面快捷键配置、固件升级或硬件调试。
---

# dongle-control

使用同级 `wb-sc/scripts/wbsc.py`。命令和参数见 [协议与调用](references/protocol.md)。

- **改遥控器实体键** → `key list` 查款式和位置，`key push --json` 预览或写入。明确请求写入时才加 `--yes`。按键名写入前确认款式。
- **点灯、枚举或查询** → `led send`、`led list` 或 `remote info`。
- **首次安装或修复 Hook** → `remote status` 检查，`ready` 为 false 时用 `remote install --yes`。排障用 `remote doctor`，卸载用 `remote uninstall --yes`。
- **核对支持的事件、安装生效或联调** → 读 [WorkBuddy Hook 事件](references/hook-events.md)。
