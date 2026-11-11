# WorkBuddy CLI 快捷键动作参考（节选）

配置文件：`~/.codebuddy/keybindings.json`
生效方式：文件变更自动应用，无需重启。`null` 表示解绑。

## 上下文（context）

`Global` `Chat` `InputBox` `Terminal` `Autocomplete` `Confirmation` `HistorySearch` `Task` `Settings` `CommandPalette` `Select` `PermissionDialog` `Help` `Plugin` `DiffDialog` `MessageSelector` `Transcript`

## 常用动作

| 动作 | 默认键 | 上下文 |
|---|---|---|
| `app:interrupt` | Ctrl+C（保留） | Global |
| `app:exit` | Ctrl+D（保留） | Global |
| `app:clearScreen` | Ctrl+L | Global |
| `app:toggleTodos` | Ctrl+T | Global |
| `app:toggleTranscript` | Ctrl+O | Global |
| `app:commandPalette` | Ctrl+Shift+P | Global |
| `history:search` | Ctrl+R | Global |
| `history:previous` / `history:next` | Up / Down | Global |
| `chat:submit` | Enter | Chat |
| `chat:cancel` | Escape | Chat |
| `chat:newline` | （见 chat:stash 说明） | Chat |
| `chat:modelPicker` | Meta+P | Chat |
| `chat:thinkingToggle` | Meta+T | Chat |
| `chat:externalEditor` | Ctrl+G / Ctrl+X Ctrl+E | Chat |
| `chat:stash` | Ctrl+S | Chat |
| `chat:imagePaste` | Ctrl+V（Win: Alt+V） | Chat |
| `chat:killAgents` | Ctrl+X Ctrl+K | Chat |
| `chat:cycleMode` | Shift+Tab（Win 另支持 Alt+M） | Chat |
| `autocomplete:accept` | Tab | Autocomplete |
| `confirm:yes` / `confirm:no` | Y/Enter, N/Escape | Confirmation |
| `task:background` | Ctrl+B | Task |
| `select:next` / `select:previous` | Down,J,Ctrl+N / Up,K,Ctrl+P | Select |

## 保留键（不可重绑）

`Ctrl+C`、`Ctrl+D`、`Ctrl+M`

## 终端复用器冲突

`Ctrl+B`（tmux 前缀）、`Ctrl+A`（screen 前缀）、`Ctrl+Z`（SIGTSTP）

## 弦序列

空格分隔，例：`ctrl+x ctrl+k`。超时 1000ms。

## 注

语音输入（`toggle-voice-recording`）属于桌面端动作，CLI 无对应动作，无法通过 keybindings.json 设置。
