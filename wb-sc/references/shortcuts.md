# WorkBuddy 桌面与 CLI 快捷键

## 核心事实（先读，避免走错路径）

| 形态 | 配置载体 | 可否用脚本改 | 生效方式 |
|---|---|---|---|
| 桌面客户端 GUI | 渲染层 `localStorage['agent-ui-keyboard-shortcuts']`，**无配置文件** | 仅能经设置界面，或 CDP 注入（需调试端口） | 立即生效 |
| 桌面客户端 GUI 的云端 | `POST /console/as/users/private-configs`，namespace `keyboard-shortcuts`，key `overrides` | 需登录态，不直接调 | 登录/启动时拉取 |
| CLI（内置 codebuddy.js / CodeBuddy Code） | `~/.codebuddy/keybindings.json` | 可以直接写文件 | 自动热加载，无需重启 |

两条硬性约束：

1. **桌面端不能靠"写配置文件"改键** —— 不存在统一的键位配置文件；`Local Storage/leveldb` 在应用运行时被独占（`LOCK` 不可写），离线写入会被进程内存与云同步覆盖。**唯一例外**是 `scope: "global"` 的 `toggle-window`，主进程另存一份 `%USERPROFILE%\.workbuddy\app\shortcut-state.json`（见下节）。
2. **桌面端采用 cloud-as-source-of-truth** —— 云端已有 `overrides` 时，本地改动会被云端覆盖；云端为空时本地改动才会被上传沉淀。因此 CDP 注入的成功率取决于云端是否已存在该 namespace 数据。

## 先判定运行时（否则会改错地方）

Agent 可能跑在两个位置，键位作用域完全不同：

| 判定依据 | 运行时 | 改 `~/.codebuddy/keybindings.json` 的效果 |
|---|---|---|
| `CLIENT_INFO_USER_AGENT_EXTENSION=CLI/x.y.z` 且 `ELECTRON_RUN_AS_NODE=1` | 桌面应用内嵌 CLI 引擎 | 只影响交互式 CLI TUI，**不影响当前 GUI 界面** |
| 在终端直接运行 `codebuddy` | 独立 CLI | 直接生效 |
| 渲染进程内（无 CLI 环境变量） | 桌面 GUI | 仍是 localStorage，与 CLI 文件无关 |

`scripts/wbsc.py detect` 会输出 `runtime.agent_runtime`、`cli_engine_version`、`launched_by_pid`、`app_version`，据此判断。桌面进程存活时，其 `Local Storage/leveldb` 必然被占用。


数据结构（桌面端）：

```json
{ "version": 1, "overrides": { "toggle-voice-recording": { "mac": "Alt+Shift+P", "win": "Alt+Shift+P" } } }
```

## 三域注册机制（global / app / context，实测于 5.3.5 构建）

`SHORTCUT_DEFINITIONS` 里每条定义都带 `scope` 字段，三值语义完全不同，改键/排障时必须先分辨：

| 维度 | `global`（仅 `toggle-window`） | `app` | `context` |
|---|---|---|---|
| 注册位置 | **主进程** `WindowManager.registerToggleWindowShortcut()` → `electron.globalShortcut.register()` | 渲染进程 React 层 keydown 监听 | 输入框组件内部（composer）监听 |
| 注册层级 | 操作系统级热键（Windows `RegisterHotKey`） | 窗口内 DOM 事件 | 组件级事件，随挂载/卸载 |
| 生效条件 | 窗口隐藏/最小化/失焦时仍生效 | 窗口需存在且获得焦点 | 输入框需获得焦点 |
| 冲突域 | 与全系统应用、输入法抢占；失败返回 `false` | 与应用内其他组件/浏览器默认键冲突 | 与输入框自身编辑行为冲突 |
| 持久化 | **双写**：`localStorage` overrides（供 UI 展示）+ `app.getPath("userData")/shortcut-state.json`（主进程启动时读，早于渲染层） | 仅 localStorage / 云端 | 仅 localStorage / 云端 |
| 生命周期 | 启动注册、退出 `unregisterToggleWindowShortcut()` | 窗口/页面级 | 组件级 |
| 失败反馈 | `globalShortcut:registrationStatus` 事件（`{success, accelerator}`），日志 `likely occupied by another application` | 保存时前端冲突校验 | 同左 |
| 跨端差异 | 云端/Web 版不支持（设置面板 `if (isCloud) list.filter(s => s.scope !== "global")`） | 各端一致 | 各端一致 |

要点：`send-message` 虽然归 `context`，但另有一条 legacy 桥（`agent-ui-submit-message-shortcut` 缓存 + `SUBMIT_MESSAGE_SHORTCUT_CHANGE_EVENT` 自定义事件），改它要两端同时更新，否则设置面板与实际输入框行为不一致。云端拉取后的 `syncBridgesAfterCloudPull()` 就是补这一步。

IPC 通道：`workbuddy:globalShortcut:updateToggleWindow`（渲染层 → 主进程）、`globalShortcut:registrationStatus`（主进程 → 渲染层广播）。

## 决策流程

1. 先跑 `detect`，确认桌面端是否运行（`leveldb_locked`）、是否有调试端口、CLI 配置是否存在。
2. 目标动作属于桌面端（如 `toggle-voice-recording`）→ 走 `plan`，默认给 GUI 操作步骤；只有用户明确接受"重启带调试端口"才走 `apply-desktop --via cdp`。
3. 目标动作属于 CLI（`chat:*` / `app:*`）→ 走 `apply-cli`，写文件即可，可靠且可回滚。
4. 任何写入前先 `check` 冲突；写入后回读校验。

## 命令

脚本路径：`scripts/wbsc.py`（Python 标准库，无需安装依赖）。

```bash
# 探测环境
python scripts/wbsc.py detect

# 列出快捷键（桌面端默认值 + CLI 自定义值）
python scripts/wbsc.py list --target desktop
python scripts/wbsc.py list --target cli

# 冲突检测（归一化修饰键顺序，"Shift+Alt+P" 与 "Alt+Shift+P" 视为同键）
python scripts/wbsc.py check --binding "Alt+Shift+P" --target both

# 生成改键方案（输出写入内容 + GUI 三步 + CDP 命令）
python scripts/wbsc.py plan --id toggle-voice-recording --binding "Alt+Shift+P"

# 桌面端：CDP 注入（未加 --yes 为 dry-run）
python scripts/wbsc.py apply-desktop --id toggle-voice-recording --binding "Alt+Shift+P" --via cdp --yes

# CLI：写 keybindings.json（未加 --yes 为 dry-run；自动备份 .bak-时间戳）
python scripts/wbsc.py apply-cli --context Chat --binding "ctrl+j" --action "chat:newline" --yes
python scripts/wbsc.py apply-cli --context Chat --binding "ctrl+s" --unbind --yes

```

## 桌面端手动改键（可靠路径，优先使用）

Windows：左侧栏底部头像 → 设置 → 快捷键设置 → 找到目标项 → 点击编辑（铅笔）→ 同时按下全部按键后松开 → 无冲突提示即成功。Mac 路径相同，按键用 `Meta`（⌘）替代 `Ctrl`。

## 已知别名与保留项

- CLI 保留键不可重绑：`Ctrl+C`、`Ctrl+D`、`Ctrl+M`。
- 终端复用器冲突：`Ctrl+B`（tmux）、`Ctrl+A`（screen）、`Ctrl+Z`（SIGTSTP）。
- `Alt+Shift` 是 Windows 键盘布局切换前缀，含该组合的自定义键可能被输入法拦截；需先在「设置 > 时间和语言 > 输入 > 高级键盘设置 > 输入语言热键」关闭 Alt+Shift 切换。
- 桌面端 `editable: false` 的动作（字号三键、`@`、`/`）不支持改键。
- 语音输入（`toggle-voice-recording`）是桌面端动作，CLI 无对应 action，无法通过 keybindings.json 设置。

## 执行注意

- 快捷键配置写入/应用重启必须先 dry-run 并让用户确认；**不要擅自重启应用**（会中断当前会话与后台任务）。
- CDP 注入后必须重载窗口才生效；页面重载会触发云端合并，若键位回退，说明云端覆盖，改用 GUI 路径即可（GUI 会同时更新云端）。
- 恢复默认：桌面端在设置项上点重置；CLI 删除 `~/.codebuddy/keybindings.json` 中对应条目或用 `--unbind`。
