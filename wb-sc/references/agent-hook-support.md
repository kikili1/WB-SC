# Agent Hook 能力与来源索引

核查日期：2026-11-16。统一入口、目标选择、安装和验收仅维护在 [通用流程](../../dongle-control/references/hook-events.md)；事件映射以 `scripts/hook_profiles.py` 为准。

- 支持本地 Windows/macOS。各宿主仅接入其配置段列出的事件；配置检查通过不等于宿主启用或灯效实测。
- Copilot 区分共享运行时与 VS Code 旧 Local 运行时。云端执行无法直接控制本机 USB，本轮不提供远程转发服务。
- TRAE 中国版路径已核实，国际版须从宿主确认实际配置路径；DeepSeek Harness 需挂载官方实验兼容桥。
- 豆包桌面端目前只查到应用插件内部事件，尚未确认普通聊天可触发本机命令的回复状态 Hook，暂不接入。这不是断言产品没有该能力。
- 多 agent/多会话仍采用最后事件决定灯态，不增加后台汇总或页面轮询。

## 官方依据

- [Codex Hooks](https://learn.chatgpt.com/docs/hooks)
- [Claude Code Hooks](https://code.claude.com/docs/en/hooks)
- [Cursor Hooks](https://cursor.com/docs/hooks)
- [GitHub Copilot Hooks](https://docs.github.com/en/copilot/concepts/customizations/hooks)
- [VS Code Agent Hooks](https://code.visualstudio.com/docs/agent-customization/hooks)
- [Gemini CLI Hooks reference](https://geminicli.com/docs/hooks/reference/)
- [TRAE Hook 配置详解](https://docs.trae.cn/ide_hook-configuration-reference)
- [TRAE Hook 启用与运行方式](https://docs.trae.cn/ide_automate-actions-with-hooks)
- [DeepSeek Harness Claude Code 兼容桥](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/hooks-claude-code/README.md)
- [DeepSeek Harness Codex 兼容桥](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/hooks-codex/README.md)
- [豆包应用插件 Agent 与端侧交互](https://open.doubao.com/apps-plugin/docs/client-framework/agent-interaction)
