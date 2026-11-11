#!/usr/bin/env python3
"""WB-SC — WorkBuddy 快捷键管理（桌面 GUI / CLI 双目标）。

用法见 SKILL.md。仅依赖 Python 标准库。
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 技能目录是要分发的：不落地 __pycache__，避免把 .pyc 一起发给别人。
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
DESKTOP_DEFS = SKILL_DIR / "references" / "desktop-shortcuts.json"

DESKTOP_STORAGE_KEY = "agent-ui-keyboard-shortcuts"
CLI_CONFIG = Path.home() / ".codebuddy" / "keybindings.json"
LEVELDB_DIR = Path.home() / ".workbuddy" / "app" / "session" / "Local Storage" / "leveldb"
CDP_PORTS = (9222, 9223, 9229)

MOD_ORDER = ["Ctrl", "Alt", "Shift", "Meta"]
MOD_ALIASES = {
    "control": "Ctrl", "ctrl": "Ctrl", "ctl": "Ctrl",
    "alt": "Alt", "opt": "Alt", "option": "Alt",
    "shift": "Shift",
    "meta": "Meta", "cmd": "Meta", "command": "Meta", "win": "Meta", "super": "Meta",
}

SYSTEM_RESERVED = {
    "Alt+F4", "Alt+Tab", "Ctrl+Alt+Del", "Alt+Esc", "Ctrl+Esc", "Ctrl+Shift+Esc",
    "Meta+Tab", "Meta+D", "Meta+L", "Meta+R", "Meta+E", "Meta+I",
}
IME_PREFIX = {"Alt+Shift"}  # Windows 键盘布局切换前缀


# ---------------------------------------------------------------- binding utils

def normalize(binding):
    """把任意写法归一化为 Ctrl+Alt+Shift+Key 的稳定比较形式。"""
    if binding is None:
        return ""
    b = str(binding).strip()
    if not b:
        return ""
    parts = [p for p in b.replace(" ", "").split("+") if p]
    if not parts:
        return ""
    mods, key = [], ""
    for p in parts:
        canon = MOD_ALIASES.get(p.lower())
        if canon:
            if canon not in mods:
                mods.append(canon)
        else:
            key = p
    mods.sort(key=lambda m: MOD_ORDER.index(m))
    if not key:  # 例如仅 "Alt+Shift"
        return "+".join(mods)
    key_out = key if len(key) > 1 and key[0].isupper() else (key.upper() if len(key) == 1 else key.capitalize())
    return "+".join(mods + [key_out])


def pretty(binding):
    """写入配置时使用的展示形式（保留用户习惯顺序，规范修饰键名）。"""
    if not binding:
        return ""
    parts = [p for p in binding.replace(" ", "").split("+") if p]
    out = []
    for p in parts:
        out.append(MOD_ALIASES.get(p.lower(), p if len(p) == 1 else (p if p.isupper() else p.capitalize())))
    return "+".join(out)


def load_desktop_defs():
    with open(DESKTOP_DEFS, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- detection

def leveldb_state():
    """三态判断 LevelDB 目录可用性：missing / writable / blocked。

    blocked 可能来自应用独占（LOCK），也可能来自沙箱只读。外部写入均不可行时
    都应当回退到 GUI 路径，因此两态合并处理是安全的。
    """
    d = LEVELDB_DIR
    if not d.exists():
        return "missing"
    probe = d / ".wbsc_probe"
    try:
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
        return "writable"
    except (PermissionError, OSError):
        return "blocked"


def cdp_alive(port, timeout=0.6):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def runtime_info():
    """判定当前 agent 运行时来源。

    这决定了"改键作用于哪里"：
    - cli-engine：agent 跑在 WorkBuddy 内嵌 CLI 上，改 ~/.codebuddy/keybindings.json 只影响交互式 CLI TUI，
      不会影响当前 GUI 界面。
    - desktop-renderer：agent 在窗口渲染进程内，键位来自 localStorage。
    """
    env = os.environ
    ua = env.get("CLIENT_INFO_USER_AGENT_EXTENSION", "")
    return {
        "agent_runtime": "cli-engine" if ua.upper().startswith("CLI") else ("desktop" if ua else "unknown"),
        "cli_engine_version": ua or None,
        "app_version": env.get("WORKBUDDY_APP_VERSION"),
        "launched_by_pid": env.get("WORKBUDDY_STARTUP_PID"),
        "electron_run_as_node": env.get("ELECTRON_RUN_AS_NODE") == "1",
        "ide_mode_disabled": env.get("CODEBUDDY_DISABLE_IDE") == "1",
        "app_asar": env.get("WORKBUDDY_APP_PATH"),
    }


def detect():
    info = {"runtime": runtime_info(),
            "leveldb_dir": str(LEVELDB_DIR), "leveldb_state": leveldb_state(),
            "cdp_ports": {}, "cli_config": str(CLI_CONFIG),
            "cli_config_exists": CLI_CONFIG.exists()}
    for p in CDP_PORTS:
        info["cdp_ports"][str(p)] = cdp_alive(p)
    return info


# ---------------------------------------------------------------- listing

def desktop_rows():
    defs = load_desktop_defs()
    return [{
        "id": s["id"], "name": s.get("labelZh", s["id"]),
        "win": s.get("defaultWin"), "mac": s.get("defaultMac"),
        "scope": s.get("scope"), "editable": s.get("editable"),
    } for s in defs["shortcuts"]]


def print_table(rows, headers):
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(str(c)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)))


def cmd_list(args):
    if args.target in ("desktop", "both"):
        print("== 桌面端快捷键（Windows 默认值；可编辑=是 表示可在设置中修改） ==")
        rows = [[r["name"], r["id"], r["win"], r["scope"], "是" if r["editable"] else "否"] for r in desktop_rows()]
        print_table(rows, ["名称", "id", "默认键(Win)", "作用域", "可编辑"])
        print()
        print(f"覆盖值存储：localStorage['{DESKTOP_STORAGE_KEY}']（无独立配置文件）")
        print()

    if args.target in ("cli", "both"):
        print("== CLI 快捷键（~/.codebuddy/keybindings.json） ==")
        if not CLI_CONFIG.exists():
            print("配置文件不存在 —— 尚未自定义过 CLI 快捷键。")
        else:
            data = json.loads(CLI_CONFIG.read_text(encoding="utf-8"))
            rows = []
            for block in data.get("bindings", []):
                for k, v in (block.get("bindings") or {}).items():
                    rows.append([block.get("context", "?"), k, v if v else "(解绑)"])
            print_table(rows, ["上下文", "按键", "动作"]) if rows else print("（无自定义绑定）")


# ---------------------------------------------------------------- check

def cmd_check(args):
    target_binding = normalize(args.binding)
    if not target_binding:
        print("无法解析键位：" + repr(args.binding))
        return 2

    print(f"目标键位：{pretty(args.binding)}  (归一化 {target_binding})")
    print()

    conflicts = []
    if args.target in ("desktop", "both"):
        for s in load_desktop_defs()["shortcuts"]:
            for plat in ("defaultWin", "defaultMac"):
                if normalize(s.get(plat)) == target_binding:
                    conflicts.append(f"桌面端 {s['id']}（{s.get('labelZh')}，{plat}）")
        # 允许覆盖自身
    if args.target in ("cli", "both"):
        cli_defaults = {
            "Ctrl+C": "app:interrupt（保留，不可重绑）",
            "Ctrl+D": "app:exit（保留，不可重绑）",
            "Ctrl+L": "app:clearScreen",
            "Ctrl+T": "app:toggleTodos",
            "Ctrl+O": "app:toggleTranscript",
            "Ctrl+Shift+P": "app:commandPalette",
            "Ctrl+R": "history:search",
            "Ctrl+X Ctrl+K": "chat:killAgents",
            "Ctrl+S": "chat:stash",
        }
        for k, v in cli_defaults.items():
            if normalize(k) == target_binding:
                conflicts.append(f"CLI {v}")

    if target_binding in SYSTEM_RESERVED:
        conflicts.append("系统保留快捷键（Windows）")
    if target_binding in IME_PREFIX:
        conflicts.append("Windows 输入法键盘布局切换前缀")

    if conflicts:
        print("冲突检测：存在 %d 项冲突" % len(conflicts))
        for c in conflicts:
            print("  ! " + c)
        return 1

    print("冲突检测：未发现冲突。")
    mods = target_binding.split("+")[:-1]
    if "Alt" in mods and "Shift" in mods:
        print("提示：Alt+Shift 是 Windows 默认的键盘布局切换前缀，部分输入法会在按住时拦截组合键；"
              "若该键无效，先在「设置 > 时间和语言 > 输入 > 高级键盘设置 > 输入语言热键」关闭 Alt+Shift 切换。")
    return 0


# ---------------------------------------------------------------- plan / guide

def find_def(shortcut_id):
    for s in load_desktop_defs()["shortcuts"]:
        if s["id"] == shortcut_id:
            return s
    return None


def cmd_plan(args):
    s = find_def(args.id)
    if not s:
        print(f"未知快捷键 id：{args.id}（用 list --target desktop 查看）")
        return 2
    if not s.get("editable"):
        print(f"{args.id}（{s.get('labelZh')}）标记为不可编辑，桌面端设置界面不提供改键。")
        return 2
    binding = pretty(args.binding)
    payload = {"version": 1, "overrides": {args.id: {"mac": binding, "win": binding}}}
    print(f"目标：{s.get('labelZh')}（{args.id}）")
    print(f"当前默认：Mac={s.get('defaultMac')} / Win={s.get('defaultWin')}")
    print(f"计划写入：{binding}（Mac 与 Win 同值；桌面端不做 Ctrl/Meta 自动映射覆盖）")
    print()
    print("写入内容（合并进 localStorage）：")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    print("生效路径：")
    print("  A 设置界面（推荐，官方通道会同步云端）")
    print("    1) 点击左侧栏底部头像 → 设置 → 快捷键设置")
    print(f"    2) 找到「{s.get('labelZh')}」一行，点击编辑（铅笔图标）")
    print(f"    3) 同时按住 {binding}（全部按下后松开）→ 确认无冲突提示 → 关闭面板")
    print("  B CDP 注入（实验性，需应用以调试端口启动）")
    print(f"    python wbsc.py apply-desktop --id {args.id} --binding {binding} --via cdp --yes")
    return 0


# ---------------------------------------------------------------- apply desktop

def find_app_exe():
    """探测 WorkBuddy 可执行文件位置，供提示重启命令时使用。"""
    candidates = [
        Path(os.environ.get("WORKBUDDY_APP_PATH", "")) / ".." / "WorkBuddy.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "WorkBuddy" / "WorkBuddy.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "WorkBuddy" / "WorkBuddy.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "WorkBuddy" / "WorkBuddy.exe",
        Path("/Applications/WorkBuddy.app/Contents/MacOS/WorkBuddy"),
    ]
    for c in candidates:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    return None


def cmd_apply_desktop(args):
    s = find_def(args.id)
    if not s:
        print(f"未知快捷键 id：{args.id}")
        return 2
    if not s.get("editable"):
        print(f"{args.id} 不可编辑。")
        return 2
    binding = pretty(args.binding)

    if args.via == "gui" or not args.via:
        return cmd_plan(args)

    # CDP 路径
    port = None
    for p in ([args.port] if args.port else CDP_PORTS):
        if cdp_alive(p):
            port = p
            break
    if port is None:
        exe = find_app_exe() or "<WorkBuddy 可执行文件>"
        print("未检测到可用的调试端口（%s）。" % ", ".join(str(x) for x in CDP_PORTS))
        print()
        print("桌面端 localStorage 无安全的离线编辑接口；要启用注入需以调试端口启动应用：")
        print("  1) 完全退出 WorkBuddy（含托盘图标）")
        print('  2) 运行："%s" --remote-debugging-port=9222' % exe)
        print("  3) 重新执行本命令")
        print()
        print("注意：重启会中断当前会话。更快的等效做法是在设置界面手动改（见 plan 的 A 路径）。")
        return 3

    if not args.yes:
        print(f"[dry-run] 将通过 CDP 端口 {port} 写入 {args.id} = {binding}")
        print("确认后追加 --yes 执行。")
        return 0

    node = shutil.which("node")
    if not node:
        managed = Path.home() / ".workbuddy" / "binaries" / "node" / "versions"
        cands = sorted(managed.glob("*/node.exe")) if managed.exists() else []
        node = str(cands[-1]) if cands else None
    if not node:
        print("未找到 node，可执行文件不可用；请改用手动改键。")
        return 4

    script = HERE / "cdp_inject.mjs"
    cmd = [node, str(script), "--port", str(port), "--id", args.id, "--binding", binding]
    if args.reload:
        cmd.append("--reload")
    print("执行：", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip())
    return r.returncode


# ---------------------------------------------------------------- apply cli

def cmd_apply_cli(args):
    ctx = args.context
    key = args.binding.strip()
    if not key:
        print("--binding 不能为空")
        return 2
    if not args.action and not args.unbind:
        print("需要 --action <namespace:action> 或 --unbind")
        return 2

    normalized = normalize(key)
    for reserved in ("Ctrl+C", "Ctrl+D", "Ctrl+M"):
        if normalized == reserved:
            print(f"{reserved} 为保留键，不可重绑。")
            return 2

    data = {"bindings": []}
    if CLI_CONFIG.exists():
        try:
            data = json.loads(CLI_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"现有配置 JSON 非法，已中止：{e}")
            return 2
        if not isinstance(data.get("bindings"), list):
            data["bindings"] = []

    block = next((b for b in data["bindings"] if b.get("context") == ctx), None)
    if block is None:
        block = {"context": ctx, "bindings": {}}
        data["bindings"].append(block)
    block.setdefault("bindings", {})

    value = None if args.unbind else args.action
    block["bindings"][key] = value

    if not args.yes:
        print(f"[dry-run] {CLI_CONFIG}  上下文 {ctx}: {key} -> {value if value else '(解绑)'}")
        print("确认后追加 --yes 执行。")
        return 0

    CLI_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if CLI_CONFIG.exists():
        backup = CLI_CONFIG.with_suffix(".json.bak-%s" % datetime.now().strftime("%Y%m%d%H%M%S"))
        shutil.copy2(CLI_CONFIG, backup)
        print(f"已备份：{backup}")
    CLI_CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入：{CLI_CONFIG}（自动生效，无需重启）")
    return 0


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(prog="wbsc", description="WB-SC WorkBuddy 快捷键管理")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="探测桌面应用/调试端口/CLI 配置文件状态")
    d.set_defaults(func=lambda a: print(json.dumps(detect(), ensure_ascii=False, indent=2)) or 0)

    p = sub.add_parser("list", help="列出快捷键")
    p.add_argument("--target", choices=["desktop", "cli", "both"], default="both")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("check", help="冲突检测")
    p.add_argument("--binding", required=True)
    p.add_argument("--target", choices=["desktop", "cli", "both"], default="both")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("plan", help="生成改键方案（含 GUI 步骤）")
    p.add_argument("--id", required=True)
    p.add_argument("--binding", required=True)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("apply-desktop", help="应用桌面端改键")
    p.add_argument("--id", required=True)
    p.add_argument("--binding", required=True)
    p.add_argument("--via", choices=["gui", "cdp"], default="gui")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--reload", action="store_true", default=True)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_apply_desktop)

    p = sub.add_parser("apply-cli", help="写入 CLI keybindings.json")
    p.add_argument("--context", required=True)
    p.add_argument("--binding", required=True)
    p.add_argument("--action", default=None)
    p.add_argument("--unbind", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_apply_cli)

    import receiver_led
    import remote_setup
    import key_push
    import vendor_info
    receiver_led.configure(sub.add_parser("led", help="独立接收器点灯"))
    key_push.configure(sub.add_parser("key", help="遥控器单格键值推送（0x39）"))
    remote_sub = remote_setup.configure(sub.add_parser("remote", help="安装、检查、自检或卸载遥控器状态 Hook"))
    vendor_info.configure(remote_sub, receiver_led.device_defaults())
    key_push.configure_reset(remote_sub)

    args = ap.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
