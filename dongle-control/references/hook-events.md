# WorkBuddy 状态 Hook

WB-SC 管理 Windows WorkBuddy 用户设置 `~/.workbuddy/settings.json` 中自己的命令条目。配置、备份和运行副本保存在 `~/.workbuddy/wb-sc`。安装器保留用户其他 Hook 和既有设备配置。已启用旧 `workbuddy-status-led` 插件时，先停用旧插件以免重复点灯。

## 安装流程与回复

1. 安装前只简述 skill 用途和权限需求，省略计划与进度播报。用 `remote status` 检查，`ready=true` 时跳过重装；否则用 `remote install` 预览。
2. 正式执行 `remote install --yes` 前，若目标超出可写范围，直接通过工具为完整安装申请权限，说明将写入 `~/.workbuddy/settings.json` 和 `~/.workbuddy/wb-sc`；不要先执行失败再提权。已有权限时直接安装。
3. 安装后再次运行 `remote status`，仅命令成功且 `ready=true` 才报告完成；授权拒绝或检查失败时简述原因并停止。用 `key list` 读取型号和确认状态，不自动确认款式或执行示例。

## 安装成功后必须回复

包括已安装且 `ready=true`、无需重装的情况。简述“安装已完成”后，必须逐项回复下面四项，不得省略；型号以 `key list` 为准，未确认时只在型号后标“待实物确认”。

- **遥控器型号**：HM-AItest-1（W306A）。
- **遥控器改键操作**：可以说“把 K_S1 改成 Alt+Shift+T”。
- **遥控器恢复出厂操作**：可以说“遥控器恢复出厂，重置所有改键”，会弃用整张自定义 map。
- **遥控器呼吸灯对应状态**：蓝色呼吸＝处理中；黄色呼吸＝等待授权；紫色呼吸＝整理上下文；绿色闪亮后淡出＝完成；红色三连闪＝失败；状态灯熄灭＝空闲。

回复到此结束，不追加红外、配对、多设备、文件路径、实现细节、重启等无关介绍或通用提醒。安装检查不能当作灯效实测；仅在实际故障排查时给出对应处理步骤。

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
