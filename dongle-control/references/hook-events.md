# 通用 Agent 状态 Hook

用户只需说“安装/检查/修复/卸载遥控器状态 Hook”。当前 agent 根据产品上下文及实际配置选择下表中的内部参数，统一调用 `wbsc.py remote install/status/doctor/uninstall`。仅支持 Windows/macOS 本地 USB；云端、远程或容器不可视为能访问本机接收器。

## 选择当前配置段

| `--agent` | 默认 Hook 文件 | 该宿主需核对的条件 |
| --- | --- | --- |
| `workbuddy` | `~/.workbuddy/settings.json` | 若启用旧状态灯插件，先避免重复注册。 |
| `codex` | `~/.codex/hooks.json` | 尊重 `CODEX_HOME`；宿主要求审核并信任定义时由用户完成。 |
| `claude` | `~/.claude/settings.json` | 尊重 `CLAUDE_CONFIG_DIR`，检查是否禁用 Hook。 |
| `cursor` | `~/.cursor/hooks.json` | 用整轮 `stop.status` 区分完成、取消和错误。 |
| `copilot` | `~/.copilot/hooks/wb-sc.json` | Copilot CLI 或 VS Code 共享 Copilot 运行时；尊重 `COPILOT_HOME`，确认本地执行。 |
| `copilot-local` | 必须指定实际文件 | VS Code 旧 Local 运行时，核对 `chat.hookFilesLocations`、`chat.useHooks` 和工作区信任。 |
| `gemini` | `~/.gemini/settings.json` | Gemini CLI；核对实际设置位置。 |
| `trae` | `~/.trae-cn/hooks.json` | 启用 Hooks、确认运行方式，避免同时导入 Claude Hook；国际版从宿主核实路径。 |
| `deepseek` | 必须指定实际文件 | DeepSeek Harness，使用下述官方兼容桥。 |

每次 Hook 命令显式带 `--agent A`，路径与默认不同时附加 `--hook-file P`。`P` 必须是当前宿主加载的 JSON 文件，不能是 TOML 或 composition YAML。来源不明确时先核查上下文，不扫描所有产品目录或默认安装到旧宿主。

## 共用流程

1. 用 `remote status --agent A [--hook-file P]` 检查。已就绪则跳过安装；`ready` 仅表示本地配置和运行副本通过检查，另看 `activation_required`。
2. 需安装或修复且用户已授权时，执行同目标的 `remote install ... --yes`；仅预览时不加 `--yes`。如需文件权限，为目标 Hook 文件及相邻 `wb-sc` 目录申请完整安装权限。
3. 安装后再检查同目标的 `remote status`，保留其中的设备配置路径 `config`，完成宿主启用/信任或桥接配置。不能自行绕过宿主信任或修改信任记录。
4. 后续硬件命令统一使用 `wbsc.py --config "设备配置绝对路径" key/led/remote ...`，包括 `key list`、`key use`、改键、重置和查询；省略 `--config` 仅兼容旧调用。配置路径已确定时直接复用。

排障用同目标的 `remote doctor`；用户授权点灯后才加 `--yes`。卸载用同目标的 `remote uninstall ... --yes`，保留设备配置、用户其他 Hook 和被用户修改的运行文件。不得将这些命令省略目标后复制执行。

### DeepSeek Harness 桥接

从当前 composition 找到已挂载的 `@deepseek-ai/dsh-hooks-claude-code` 或 `@deepseek-ai/dsh-hooks-codex` 及其 `configPath`，复用该 JSON 文件作为 `P`，不同时挂载两种桥。没有桥时，按 [官方说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/experimental/hooks-claude-code/README.md) 向实际 composition 添加插件项：

```yaml
- name: '@deepseek-ai/dsh-hooks-claude-code'
  config:
    configPath: /absolute/path/to/hooks.json
```

保留其他插件，回读核对并按宿主要求重载。安装器只处理 Hook JSON 和运行副本；未找到 composition、桥不可用或缺少权限时，报告尚待桥接，不能声称已生效。桥属于实验组件，仅支持配置段列出的事件。

## 验收与回复

新会话中实际触发请求、回复完成及可用的等待事件，才能确认事件链路；手动点灯不能代替。缺少的事件不声称支持。多个 agent/会话共用一个灯时仍由最后一次事件决定状态。

首次安装说明真实结果及四项：型号（`--config` 对应的 `key list`，未确认则注明）、改键示例、整机恢复出厂说法、当前宿主接入的灯态。蓝色呼吸＝处理中；黄色呼吸＝等待；紫色呼吸＝整理上下文；绿色闪亮后淡出＝完成；红色三连闪＝失败；熄灭＝空闲。

检查、已就绪或普通修复仅回复结果与必要下一步。文件已安装但仍需启用/信任时明确说明，不回复全部生效。能力限制与来源见 [支持索引](../../wb-sc/references/agent-hook-support.md)。
