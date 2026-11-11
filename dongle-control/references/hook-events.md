# WorkBuddy 状态 Hook

WB-SC 管理 Windows WorkBuddy 用户设置 `~/.workbuddy/settings.json` 中自己的命令条目。配置、备份和运行副本保存在 `~/.workbuddy/wb-sc`。安装器保留用户其他 Hook 和既有设备配置。已启用旧 `workbuddy-status-led` 插件时，先停用旧插件以免重复点灯。

## 安装流程与回复

1. 安装前只简述 skill 用途和权限需求，省略计划与进度播报。用 `remote status` 检查，`ready=true` 时跳过重装；否则用 `remote install` 预览。
2. 正式执行 `remote install --yes` 前，若目标超出可写范围，直接通过工具为完整安装申请权限，说明将写入 `~/.workbuddy/settings.json` 和 `~/.workbuddy/wb-sc`；不要先执行失败再提权。通常只需 agent 沙箱授权，无需 Windows 管理员权限，也不承诺永久免授权。已有权限时直接安装。
3. 安装后再次运行 `remote status`，仅命令成功且 `ready=true` 才报告完成；授权拒绝或检查失败时简述原因并停止。完成回复只介绍安装结果、`key list` 中的款式/确认状态和两个示例：“把 K_S1 改成 Alt+Shift+T”“重置遥控器，弃用全部自定义配置”。未确认的款式标明“待实物确认”，不当作自动识别结果，不自动执行示例或确认款式。提示新建 WorkBuddy 会话加载 Hook，仍使用旧配置时再手动重启。

排障用 `remote doctor`，带 `--yes` 才测试灯态；卸载用 `remote uninstall --yes`。`ready=true` 仅表示本地安装检查通过；实际 busy/done 灯效需在新会话提交消息和结束回复时验证。

| 事件 | 状态 | 触发条件 |
|---|---|---|
| `SessionStart`、`SessionEnd` | idle | 会话开始或结束 |
| `UserPromptSubmit` | busy | 用户提交请求 |
| `Stop` | done | Agent 完成回复 |
| `StopFailure` | error | 运行时报告回合失败 |
| `PermissionRequest` | wait | 需要人工授权 |
| `Notification` | wait | 载荷命中权限相关关键词 |
| `PreCompact` | compact | 开始整理上下文 |

实际派发取决于 WorkBuddy 版本和事件发生条件。`status` 校验本地安装，实测覆盖范围由具体会话触发结果决定。取消、强退可能没有结束事件。多会话共享一只遥控器时灯态跟随最近事件。

安装时验证并固定 Python 路径。普通 Windows 路径由 WorkBuddy 的 shell 直接调用 Python，需特殊引用的解释器路径走 PowerShell 兼容启动。Hook 只写 HID，一次枚举，跳过回执，发送失败输出 stderr 并继续对话。Hook 不保存正文。
