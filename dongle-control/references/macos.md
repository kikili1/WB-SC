# macOS 安装与验收

Windows 使用独立的原生后端，以下步骤仅适用于 macOS。

## 解释器与依赖

快捷键管理只需要 Python。Dongle 和状态 Hook 额外需要 `hidapi==0.15.0`（导入名为 `hid`，不要安装名称为 `hid` 的其他包）。使用与机器架构一致的 Python，优先使用已有的可写虚拟环境；没有时可建立专用环境：

```bash
python3 -m venv "$HOME/.workbuddy/wb-sc-venv"
"$HOME/.workbuddy/wb-sc-venv/bin/python3" -m pip install hidapi==0.15.0
```

上面命令是安装指引，技能不会自动创建环境或安装依赖。后续用这个解释器执行脚本。以下命令从 `wb-sc` 技能目录运行；将 `python3` 替换为该解释器的绝对路径。安装器会选择可用的托管解释器或当前解释器，清单记录最终路径；`remote doctor` 检查该解释器能否导入 HIDAPI。

```bash
python3 scripts/wbsc.py detect
python3 scripts/wbsc.py remote status
python3 scripts/wbsc.py remote install
```

正式安装、修复、卸载沿用 [Hook 安装流程](hook-events.md)。安装使用 POSIX 引用的绝对 Python 路径，写入 `~/.workbuddy/settings.json` 和 `~/.workbuddy/wb-sc`，不使用 PowerShell；解释器或虚拟环境移动后应重新安装。无依赖时硬件功能报错，但不阻止快捷键管理。

## 设备诊断

```bash
python3 scripts/wbsc.py remote doctor
python3 scripts/wbsc.py led list
```

`led list` 中的 `path` 是当前系统 HID 路径字节的十六进制表示，仅作为不透明标识使用；多设备时完整复制到 `--path` 或设备配置。Windows 保存的设备路径不能用于 Mac。描述符无法读取时拒绝发送，不假设长度。设备打开失败按实际错误检查连接、系统隐私权限或其他软件占用；不要默认使用 sudo，也不要在未经确认时更改系统权限。

## 真机验收

1. 在 Intel 和 Apple Silicon 的目标 Mac 上分别运行 `detect`、快捷键列表及冲突检查，确认 Mac 默认值；用 GUI 修改一个键位验证实际效果。CLI 验证 Ctrl 组合仍按原值保存。
2. `led list` 验证厂商集合及描述符长度；不接设备、多设备、拔出设备均应明确报错，不能误选或挂起。
3. 用户授权点灯后用 `remote doctor --yes` 测试并实际观察灯效；仅收到转发确认不等于灯效成功。
4. 用户确认款式并授权改键后，验证一键改写与单键恢复。只有有效 `saved` 回执才报告保存；断连或超时报告未知，不自动重试。整机重置会弃用所有覆盖并重启，只在明确授权后验收。
5. `remote info --yes` 仅在授权查询后执行；无 CS/版本数据时报告未取得信息，不能把转发确认当查询成功。
6. 安装后验证 `remote status`，再在新会话提交消息、等待完成和授权，确认 Hook 触发及灯态；检查用户其他设置和 Hook 保留。
7. 在隔离测试用户或环境验证重装、升级、卸载及有空格/引号的路径；保留自定义配置、用户修改的运行文件和其他 Hook。

CDP 另需支持内置 fetch/WebSocket 的 Node.js（建议 22+）及已开启的调试端口。全局唤醒、发送消息通过 GUI 修改；其余动作写入当前平台后重载回读，后续云同步仍可能覆盖。
