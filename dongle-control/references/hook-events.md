# WorkBuddy 状态 Hook

WB-SC 管理 Windows WorkBuddy 用户设置 `~/.workbuddy/settings.json` 中自己的命令条目。配置、备份和运行副本保存在 `~/.workbuddy/wb-sc`。安装器保留用户其他 Hook 和既有设备配置。已启用旧 `workbuddy-status-led` 插件时，先停用旧插件以免重复点灯。

1. 用 `remote status` 检查注册、当前版本、运行副本、Python 和接收器配置。各项通过时 `ready` 为 true。
2. 用 `remote install` 预览，`remote install --yes` 安装或修复。已有当前版本时直接返回。安装后新建 WorkBuddy 会话，确认提交消息后亮 busy，回合结束亮 done。
3. 用 `remote doctor` 检查配置和枚举结果。带 `--yes` 才发送测试灯态。用 `remote uninstall --yes` 移除 WB-SC 的注册和可安全删除的运行文件。

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
