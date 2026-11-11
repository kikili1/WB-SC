# 遥控器键值真值表

来源：`E:/W306A 蓝牙组合键值真值表.docx` + `rc_key.h` 的 `K_HID`/`K_HID_R` 宏。
脚本实现：`scripts/keymap_rc.py`（解析 + 组帧）、`scripts/key_push.py`（推送）。

## 编码规则

| 形态 | 含义 |
|---|---|
| `0x6MUU` | 左侧修饰键 + 主键。M 为 4 bit 掩码，UU 为 HID usage |
| `0x7MUU` | 右侧修饰键 + 主键 |
| `0x00UU` | 只发主键，不带修饰 |
| `0x6M00` / `0x7M00` | 只发修饰键 |

同一个键值只能使用同一侧的修饰键，左右不可混用。

## 修饰键掩码（示例：+Enter）

| M | 二进制 | 修饰键 | 左侧 | 右侧 |
|---|---|---|---|---|
| 0 | 0000 | 无 | 0x0028 | 0x0028 |
| 1 | 0001 | Ctrl | 0x6128 | 0x7128 |
| 2 | 0010 | Shift | 0x6228 | 0x7228 |
| 3 | 0011 | Ctrl+Shift | 0x6328 | 0x7328 |
| 4 | 0100 | Alt | 0x6428 | 0x7428 |
| 5 | 0101 | Ctrl+Alt | 0x6528 | 0x7528 |
| 6 | 0110 | Shift+Alt | 0x6628 | 0x7628 |
| 7 | 0111 | Ctrl+Shift+Alt | 0x6728 | 0x7728 |
| 8 | 1000 | Win/GUI | 0x6828 | 0x7828 |
| 9 | 1001 | Ctrl+Win | 0x6928 | 0x7928 |
| A | 1010 | Shift+Win | 0x6A28 | 0x7A28 |
| B | 1011 | Ctrl+Shift+Win | 0x6B28 | 0x7B28 |
| C | 1100 | Alt+Win | 0x6C28 | 0x7C28 |
| D | 1101 | Ctrl+Alt+Win | 0x6D28 | 0x7D28 |
| E | 1110 | Shift+Alt+Win | 0x6E28 | 0x7E28 |
| F | 1111 | Ctrl+Shift+Alt+Win | 0x6F28 | 0x7F28 |

## 常用主键 usage（HID Keyboard/Keypad 页 0x07）

| 按键 | UU |
|---|---|
| A–Z | 04–1D |
| 1–9 | 1E–26 |
| 0 | 27 |
| Enter / Esc / 退格 / Tab / 空格 | 28 / 29 / 2A / 2B / 2C |
| 减号 / 等号 / 左方括号 / 右方括号 | 2D / 2E / 2F / 30 |
| Caps Lock | 39 |
| F1–F12 | 3A–45 |
| Print Screen / Scroll Lock / Pause | 46 / 47 / 48 |
| Insert / Home / Page Up | 49 / 4A / 4B |
| Delete / End / Page Down | 4C / 4D / 4E |
| 右 / 左 / 下 / 上 | 4F / 50 / 51 / 52 |
| 小键盘 Enter | 58 |
| 小键盘 1–9 / 0 | 59–61 / 62 |

## 改键示例

| 目标 | 键值 |
|---|---|
| Enter | 0x0028 |
| 左 Ctrl | 0x6100 |
| 左 Ctrl + C | 0x6106 |
| 左 Alt + F4 | 0x643D |
| 左 Win + R | 0x6815 |
| 左 Shift + Alt + T | 0x6617 |
| 左 Alt + Shift + W | 0x661A |
| 左 Ctrl + D | 0x6107 |

## 遥控器款式

按键的**物理位置**随款式变化，键值编码不变。款式记录在 `~/.workbuddy/wb-sc/config.json` 的 `variant` 字段，用 `wbsc.py key use --variant <款式>` 切换；表在 `scripts/keymap_rc.py` 的 `VARIANTS`。

`variant_confirmed` 表示该款式的位置已在实物上核对过。新装机写 `false`，此时 `key push --name` 会拒绝执行（避免按别的款式位置改错键），`key use` 之后置 `true`。老配置没有该字段时按已确认处理。

| 款式 | 说明 | 收录状态 |
|---|---|---|
| `HM-AItest-1` | W306A 样机，1 列 9 行（PA02/PA12/PA11/PA01/PA05/PA04/PA03/PB00/PB01） | 已收录，默认款式 |

其他款式待补充：新增时照抄 `VARIANTS` 的结构，位置必须按实际 PCB/按键排布核对，不能从其他款式照抄。

## W306A 键位与键值（HM-AItest-1）

实物为 **1 列 9 行**，行号就是固件 `rc_key.h` 的 `rckey_row[]` 下标，也是 0x39 报文里的 row 字节。
逻辑键号来自实测：按实物顺序逐键按下收到 `13279685`，即
物理第1位→行0、第2位→行2、第3位→行1、第4位→行6、第5位→行8、第6位→行5、第7位→行7、第8位→行4，
缺的那个位置是行3（PA1），实物上没有可按的键。

出厂码值（2026-11-11 起，源码 `rc_key.c` 的 `FACTORY_BLE_KEYS` 与下表一致）：

| 键名 | 位置 | GPIO | 逻辑键 | 出厂码值 | 含义 |
|---|---|---|---|---|---|
| K_S1 | C0/R0 | PA02 | 1 | 0x6107 | Ctrl+D |
| K_S3 | C0/R2 | PA11 | 2 | 0x0028 | Enter |
| K_S2 | C0/R1 | PA12 | 3 | 0x002A | Backspace |
| IO_KEY2 | C0/R6 | PA03 | 4 | 0x3101 | 鼠标左键 |
| IO_KEY4 | C0/R8 | PB01 | 5 | 0x3101 | 鼠标左键 |
| IO_KEY1 | C0/R5 | PA04 | 6 | 0x3102 | 鼠标右键 |
| IO_KEY3 | C0/R7 | PB00 | 7 | 0x3102 | 鼠标右键 |
| SW_P1 | C0/R4 | PA05 | 8 | 0x5002 | 陀螺仪开关（切换鼠标/陀螺仪模式 + 校准） |
| PA1 | C0/R3 | PA01 | 9 | 0x5002 | 同上（实物无按键） |

## 专用码（非键盘页）

| 键值 | 名称 | 固件处理 | 可用别名 |
|---|---|---|---|
| 0x3101 | 鼠标左键 | `case 0x31` → `MOUSE_KKEY` bit0 | `ml`、`lmb`、`左键`、`鼠标左键` |
| 0x3102 | 鼠标右键 | bit1 | `mr`、`rmb`、`右键`、`鼠标右键` |
| 0x3104 | 鼠标中键 | bit2 | `mm`、`mmb`、`中键`、`鼠标中键` |
| 0x5002 | 陀螺仪开关 | `case 0x50` → 切换 `fm_open`；`fgy_inside` 时置 `fgyro_calib` | `gyro`、`touch`、`陀螺仪` |
| 0x5001 | FN（`K_FN`） | 该段仅匹配 `K_TOUCH`，其余忽略 | `fn` |

`combo_key_valid()` 只校验 0x6xxx/0x7xxx，所以 0x31xx 与 0x50xx 都能经 0x39 写入并被接收。

## 推送报文

```
05 39 05 <token> <col> <row> <hi> <lo>      PC -> 接收器（HID 输出报告，补零到 64 字节）
39 <token> <status>                         回执，status 0=saved 1=参数非法 2=保存失败 3=忙
```

接收器剥掉首字节 `05`（报告 ID）后，BLE 侧为 `39 05 <token> <col> <row> <hi> <lo>` 共 7 字节。
写入会落到 VM，掉电保留；遥控器回到出厂前一直使用下发的键表。

`--restore` 用的是本表记录的键值，本表与固件 `rc_key.c` 的 `FACTORY_BLE_KEYS` 保持一致，因此恢复到的是**固件真实出厂值**
（2026-11-11 起：Ctrl+D / Enter / Backspace / 左键×2 / 右键×2 / 陀螺仪×2）。
若曾把本表改成过自定义值，`--restore` 会恢复那个自定义值而非出厂值——改表前务必确认这一点。
