---
name: dongle-control
description: 在 Windows 或 macOS 控制 USB Dongle 遥控器的改键、配置重置、点灯和查询，或为当前本地 agent 安装、检查、修复、卸载回复状态 Hook。不用于桌面快捷键、固件升级或硬件调试。
---

# dongle-control

统一运行同级 `wb-sc/scripts/wbsc.py`。Windows 使用 Python 3.8+ 和原生 HID；macOS 使用 Python 3.10+ 与 `hidapi==0.15.0`，依赖和权限见 [macOS 指引](references/macos.md)。

## 按任务读取

- **安装、检查、修复、卸载状态 Hook**：读 [通用安装流程](references/hook-events.md)。由当前 agent 选择自己的配置段，不提供分宿主入口，不根据模型名称或目录存在推断宿主。
- **遥控器改键、单键恢复、整机重置、点灯或查询**：读 [命令与回执](references/protocol.md)。已有当前宿主安装时，将其 `remote status` 返回的 `config` 作为全局 `--config` 参数，确保操作与 Hook 使用同一设备配置；同一任务沿用已确定的路径，无需每次重新检查。

## 执行与结果

- 默认面向 HM-AItest-1（W306A），按键名写入前核对款式；已有确认记录时不重复确认。`key list` 查看，`key use` 记录实物确认。
- 用户明确要求写入、恢复或重置时直接加 `--yes`；仅讨论或预览时不加。不要额外重复预览或请求相同授权。
- 单键恢复用 `key push --restore`，整机恢复用 `remote reset`，两者不可替代。仅 `saved` / `discarded` 分别表示遥控器确认保存 / 弃用配置；超时报告未知，不自动重发。
- 改键后只简述按键和新功能。默认隐藏命令、键码、JSON 和回执细节；失败时说明原因及必要下一步，不把 USB 写入成功当保存成功。
- Hook 配置检查、宿主启用/信任和真实灯效分别判断；未实测时如实说明。
