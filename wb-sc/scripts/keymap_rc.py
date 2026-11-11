"""W306A 蓝牙组合键值真值表：键名解析 + 0x39 单格推送报文组装。

数据来源：
  - E:/W306A 蓝牙组合键值真值表.docx（0x6MUU/0x7MUU 规则、修饰掩码、主键码）
  - apps/app/src/mbox_flash/remotecontrol/rc_key.h（K_HID/K_HID_R 宏、K_S1..K_S3 出厂值）

编码规则：
  0x6MUU  左侧修饰键 + 主键       M = 4bit 修饰掩码，UU = HID usage
  0x7MUU  右侧修饰键 + 主键
  0x00UU  只发主键（无修饰）
  0x6M00  只发修饰键
同一组合键只能使用同一侧的修饰键，左右不可混用。
"""
COLUMNS = 7
ROWS = 9        # 与固件 rc_key.h 的 KEYMAP_ROWS 一致（行号 0~8）

MODIFIER_MASK = {
    "ctrl": 0x1, "control": 0x1,
    "shift": 0x2,
    "alt": 0x4,
    "win": 0x8, "gui": 0x8, "meta": 0x8, "cmd": 0x8, "super": 0x8,
}
MODIFIER_LABEL = ((0x1, "Ctrl"), (0x2, "Shift"), (0x4, "Alt"), (0x8, "Win"))

# 遥控器款式 -> 物理按键位置表。位置是 (列, 行)，出厂值取自对应工程的
# FACTORY_BLE_KEYS 与 rc_key.h。新增款式照抄一份结构即可，位置必须按实际 PCB 核对。
# 行号即固件 rckey_row[] 下标（0~8），也就是 0x39 报文里的 row。
DEFAULT_VARIANT = "HM-AItest-1"

# HM-AItest-1 的实测对应关系：按实物顺序逐键按下得到 "13279685"，即
# 物理第1位->行0、第2位->行2、第3位->行1、第4位->行6、第5位->行8、
# 第6位->行5、第7位->行7、第8位->行4；缺的那个位置是行3（PA1 触摸键），实物上没有可按的键。
# logical = 该实体键在实物排布里的顺序号。
# factory = 固件 rc_key.c 的 FACTORY_BLE_KEYS，即出厂码值（2026-11-11 起为
# Ctrl+D / Enter / Backspace / 两个鼠标左键 / 两个鼠标右键 / 两个陀螺仪开关）。
VARIANTS = {
    "HM-AItest-1": {
        "note": "W306A 样机，1 列 9 行（PA02/PA12/PA11/PA01/PA05/PA04/PA03/PB00/PB01）",
        "keys": {
            "K_S1":    {"pos": (0, 0), "logical": 1, "factory": 0x6107, "note": "PA02 逻辑键1"},
            "K_S3":    {"pos": (0, 2), "logical": 2, "factory": 0x0028, "note": "PA11 逻辑键2"},
            "K_S2":    {"pos": (0, 1), "logical": 3, "factory": 0x002A, "note": "PA12 逻辑键3"},
            "IO_KEY2": {"pos": (0, 6), "logical": 4, "factory": 0x3101, "note": "PA03 逻辑键4"},
            "IO_KEY4": {"pos": (0, 8), "logical": 5, "factory": 0x3101, "note": "PB01 逻辑键5"},
            "IO_KEY1": {"pos": (0, 5), "logical": 6, "factory": 0x3102, "note": "PA04 逻辑键6"},
            "IO_KEY3": {"pos": (0, 7), "logical": 7, "factory": 0x3102, "note": "PB00 逻辑键7"},
            "SW_P1":   {"pos": (0, 4), "logical": 8, "factory": 0x5002, "note": "PA05 编码器按压 逻辑键8"},
            "PA1":     {"pos": (0, 3), "logical": 9, "factory": 0x5002, "note": "PA01 触摸键 逻辑键9（实物无按键）"},
        },
    },
}


def variant_names():
    return sorted(VARIANTS)


def variant_keys(name=None):
    """取某款式的按键表；name 为空时用默认款式。"""
    name = name or DEFAULT_VARIANT
    if name not in VARIANTS:
        raise ValueError("未收录的遥控器款式 %r；已收录：%s"
                         % (name, "、".join(variant_names())))
    return VARIANTS[name]["keys"]

_USAGE = {}
for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _USAGE[_ch] = 0x04 + _i
for _i, _ch in enumerate("123456789"):
    _USAGE[_ch] = 0x1E + _i
_USAGE.update({
    "0": 0x27, "enter": 0x28, "return": 0x28, "esc": 0x29, "escape": 0x29,
    "backspace": 0x2A, "back": 0x2A, "tab": 0x2B, "space": 0x2C, "spacebar": 0x2C,
    "-": 0x2D, "minus": 0x2D, "=": 0x2E, "equal": 0x2E, "equals": 0x2E,
    "[": 0x2F, "leftbracket": 0x2F, "]": 0x30, "rightbracket": 0x30,
    "capslock": 0x39, "caps": 0x39,
    "printscreen": 0x46, "prtsc": 0x46, "scrolllock": 0x47, "pause": 0x48,
    "insert": 0x49, "ins": 0x49, "home": 0x4A, "pageup": 0x4B, "pgup": 0x4B,
    "delete": 0x4C, "del": 0x4C, "end": 0x4D, "pagedown": 0x4E, "pgdn": 0x4E,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "numenter": 0x58, "kpenter": 0x58,
})
for _i in range(1, 10):
    _USAGE["kp%d" % _i] = 0x58 + _i
_USAGE["kp0"] = 0x62
for _i in range(1, 13):
    _USAGE["f%d" % _i] = 0x39 + _i

_PRETTY = {
    "enter": "Enter", "return": "Enter", "esc": "Esc", "escape": "Esc",
    "backspace": "Backspace", "back": "Backspace", "tab": "Tab", "space": "Space",
    "spacebar": "Space", "capslock": "Caps Lock", "caps": "Caps Lock",
    "printscreen": "Print Screen", "prtsc": "Print Screen",
    "scrolllock": "Scroll Lock", "pause": "Pause",
    "insert": "Insert", "ins": "Insert", "home": "Home",
    "pageup": "Page Up", "pgup": "Page Up", "delete": "Delete", "del": "Delete",
    "end": "End", "pagedown": "Page Down", "pgdn": "Page Down",
    "right": "Right", "left": "Left", "down": "Down", "up": "Up",
    "numenter": "Num Enter", "kpenter": "Num Enter",
    "minus": "-", "equal": "=", "equals": "=",
    "leftbracket": "[", "rightbracket": "]",
}


def _pretty(name):
    if name in _PRETTY:
        return _PRETTY[name]
    if len(name) == 1:
        return name.upper()
    if name.startswith("kp") and name[2:].isdigit():
        return "Num " + name[2:]
    if name.startswith("f") and name[1:].isdigit():
        return name.upper()
    return name


_USAGE_LABEL = {}
for _name, _code in _USAGE.items():
    _USAGE_LABEL.setdefault(_code, _pretty(_name))

# 非键盘页的专用码：0x31xx = 鼠标按键（固件 matrix_key_map_deal 的 case 0x31 -> MOUSE_KKEY），
# 0x50xx = 功能键（0x5002 在固件里切换鼠标/陀螺仪模式并触发陀螺仪校准）。
_SPECIAL = {
    0x3101: "鼠标左键", 0x3102: "鼠标右键", 0x3104: "鼠标中键",
    0x5001: "FN", 0x5002: "陀螺仪开关",
}
_SPECIAL_ALIAS = {
    "ml": 0x3101, "mouseleft": 0x3101, "lmb": 0x3101, "左键": 0x3101, "鼠标左键": 0x3101,
    "mr": 0x3102, "mouseright": 0x3102, "rmb": 0x3102, "右键": 0x3102, "鼠标右键": 0x3102,
    "mm": 0x3104, "mousemiddle": 0x3104, "mmb": 0x3104, "中键": 0x3104, "鼠标中键": 0x3104,
    "gyro": 0x5002, "touch": 0x5002, "陀螺仪": 0x5002, "陀螺仪开关": 0x5002,
    "fn": 0x5001,
}


def usage_of(text):
    key = text.strip().lower()
    if key in _SPECIAL_ALIAS:
        return _SPECIAL_ALIAS[key]
    if key in _USAGE:
        return _USAGE[key]
    raise ValueError("无法识别的主键 %r；可用 0xNN、字母/数字、F1-F12、Enter/Esc/Tab/Space、"
                     "鼠标左键/右键（ml/mr）、陀螺仪（gyro）等" % text)


def parse_key(text):
    """把 "Alt+Shift+T" / "0x6617" / "T" / "左Ctrl" 式输入解析成 16 位键值。"""
    raw = str(text).strip()
    if not raw:
        raise ValueError("键值不能为空")
    lowered = raw.lower()
    if lowered.startswith("0x") or (len(raw) == 4 and all(c in "0123456789abcdefABCDEF" for c in raw)):
        value = int(raw, 16)
        if not 0 <= value <= 0xFFFF:
            raise ValueError("键值超出 16 位范围：%r" % raw)
        return value

    parts = [p.strip() for p in raw.split("+") if p.strip()]
    if not parts:
        raise ValueError("键值不能为空")
    base, mods = parts[-1], parts[:-1]
    if not mods and base.lower() in MODIFIER_MASK:
        mods, base = [base], None

    left = right = 0
    for item in mods:
        name = item.strip().lower()
        if name.startswith("左"):
            name = name[1:]
        elif name.startswith("右"):
            name = "r" + name[1:]
        side_right = name.startswith("r") and name[1:] in MODIFIER_MASK
        lookup = name[1:] if side_right else name
        if lookup not in MODIFIER_MASK:
            raise ValueError("未知修饰键 %r（支持 Ctrl/Shift/Alt/Win，右侧加 R 前缀）" % item)
        if side_right:
            right |= MODIFIER_MASK[lookup]
        else:
            left |= MODIFIER_MASK[lookup]
    if left and right:
        raise ValueError("左右修饰键不能混用在同一个键值里")

    usage = usage_of(base) if base else 0
    if not left and not right:
        return usage
    if right:
        return 0x7000 | (right << 8) | usage
    return 0x6000 | (left << 8) | usage


def describe(value):
    """0x6617 -> "Shift+Alt+T"；普通键返回可读名。"""
    value &= 0xFFFF
    if value in _SPECIAL:
        return _SPECIAL[value]
    if (value & 0xE000) != 0x6000:          # 0x6xxx / 0x7xxx 才是组合键
        return _USAGE_LABEL.get(value, "0x%04X" % value)
    mask = (value >> 8) & 0x0F
    usage = value & 0xFF
    side = "R" if value & 0x1000 else ""
    names = [side + label for bit, label in MODIFIER_LABEL if mask & bit]
    if not usage:
        return ("右" + "+".join(names)) if side else ("左" + "+".join(names))
    names.append(_USAGE_LABEL.get(usage, "0x%02X" % usage))
    return "+".join(names)


def cell_packet(token, column, row, value):
    """组装 0x39 单格推送报文：05 39 05 token col row hi lo。"""
    if not 0 <= column < COLUMNS:
        raise ValueError("列号必须在 0~%d 之间" % (COLUMNS - 1))
    if not 0 <= row < ROWS:
        raise ValueError("行号必须在 0~%d 之间" % (ROWS - 1))
    if not 0 <= value <= 0xFFFF:
        raise ValueError("键值超出 16 位范围")
    return bytes((0x05, 0x39, 0x05, token & 0xFF, column, row,
                  (value >> 8) & 0xFF, value & 0xFF))
