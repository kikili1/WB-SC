# macOS 依赖与验收

使用 macOS 12+（Intel / Apple Silicon）、Python 3.10+，安装与实际执行使用同一个解释器。优先复用已有的可写虚拟环境；缺少 HIDAPI 时可准备：

```bash
python3 -m venv "$HOME/.wb-sc/venv"
"$HOME/.wb-sc/venv/bin/python3" -m pip install hidapi==0.15.0
```

导入名为 `hid`，不要安装名为 `hid` 的其他包。后续使用该解释器绝对路径运行 `wbsc.py`；不运行 PowerShell 或 `run.ps1`。解释器移动后重新安装 Hook。安装和诊断统一沿用 [当前目标的参数与流程](hook-events.md)，不单独运行默认目标命令。

`led list` 的 `path` 是当前系统设备路径的不透明十六进制标识，不跨平台复用；多设备时完整复制到当前设备配置或 `--path`。描述符读取失败、设备打不开时按实际错误检查连接和系统权限，不默认使用 sudo。

真机验收：先枚举并确认唯一接收器；用户授权后验证点灯和回执；在新会话验证宿主事件和灯效。改键、单键恢复和整机重置仅在用户明确要求时测试。分别报告模拟检查、宿主事件和硬件实测结果；Windows 上的模拟 Mac 测试不能替代 Intel / Apple Silicon 真机验收。
