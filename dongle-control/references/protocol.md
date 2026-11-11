# Dongle 命令与回执

在 Windows 使用 Python 3.8+ 运行同级 `wb-sc/scripts/wbsc.py`。以下省略脚本路径。可使用 WorkBuddy 自带的 `%USERPROFILE%\.workbuddy\binaries\python\versions\<版本>\python.exe`。

| 命令 | 用途 |
|---|---|
| `led list` | 枚举匹配的厂商 HID 集合 |
| `key list` | 显示款式确认状态、物理键名、列行和出厂值 |
| `key use --variant HM-AItest-1` | 用户核对实体款式后记录确认 |
| `key push --name K_S1 --key "Alt+Shift+T" --json` | 预览。用户明确要求写入时加 `--yes` |
| `key push --name K_S1 --restore --json` | 预览出厂值。用户明确要求恢复时加 `--yes` |
| `key push --col 0 --row 0 --key 0x6617 --json` | 用户给出确切矩阵位置时按坐标预览 |
| `led send busy --yes` | 手动点灯，等待链路回包 |
| `remote reset --json` | 预览弃用全部主机覆盖；明确要求重置时加 `--yes` |
| `remote info --yes` | 查询遥控器 CS、版本等，需固件支持 `0x1F` |

按键名写入使用已确认的款式。已知坐标时可以直接传列和行，均从 0 起。先展示目标位置和键值。款式和键值编码见同级 Skill 的 [键值真值表](../../wb-sc/references/key-values.md)。

## 单键重置

用户明确要求恢复 K_S1 时执行 `key push --name K_S1 --restore --json --yes`，其他键替换键名。执行前核对款式、位置和表中的出厂值；未确认款式时先由用户核对实物，再用 `key use --variant <款式>` 记录。`--restore` 写回款式表记录的值，仅影响指定按键。只有回执 `outcome=saved` 表示已保存；`unknown` 时报告结果未知，不自动重发。整机弃用改键 map 使用下面的 `remote reset`，不能用卸载 Hook 或单键恢复代替。

## 0x39 单键

发送 `05 39 05 <token> <col> <row> <value_hi> <value_lo>`，仅修改一个矩阵位置。读句柄在发送前打开。Dongle 回传固定 HID 报告 `08 39 <token> <status> 00 ... 00`，用报告 ID、命令字、令牌、状态和填充校验结果。

`key push --json` 在参数解析后输出一条 JSON。字段 `outcome` 用于判断结果，解析成功时还可获得 `variant`、`variant_confirmed`、`col`、`row`、`value`、`token`、`tx`。收到有效遥控器回执时带 `status`。

| outcome | status | 退出码 | 含义 |
|---|---|---|---|
| `preview` |  | 0 | 仅生成报文 |
| `saved` | 0 | 0 | 遥控器确认已保存 |
| `rejected` | 1 | 1 | 参数被遥控器拒绝 |
| `save_failed` | 2 | 1 | 遥控器保存失败 |
| `busy` | 3 | 1 | 遥控器忙，松开按键或等恢复出厂完成 |
| `unknown` |  | 1 | 发送阶段失败或未收到有效回执，先核对实际键值 |
| `error` |  | 1 | 发送前校验或设备打开失败 |

命令行参数错误由解析器报错并返回 2。超时后不会自动重发。

## 0x43 状态和 0x1F 查询

`0x43` 帧为 `05 43 01 <state>`。六种状态依序为 idle、busy、done、error、wait、compact。USB 写入成功只表明主机提交了报告。收到 `08 AA` 表明接收器回应了链路命令，遥控器灯效需实测。部分旧固件仅接受状态 0 至 3。

`0x1F` 查询帧为 `04 1F 00 00 00 00 00 00 72`。遥控器的 `08 18` 和 `08 13` 报告分别携带 CS 和版本分片。只收到 `08 AA` 或查询确认时，仍缺少 CS 和版本。当前部分 W306 固件未提供该查询。

## 整机配置重置（0x44）

`remote reset --json` 预览；用户明确要求整机重置或弃用自定义 map 后，用 `remote reset --json --yes` 发送一次 `05 44 02 01 <token>`。可用 `--vid`、`--pid`、`--path` 选择接收器，`--timeout` 设置等待秒数。无需按款式逐键写回。

恢复出厂会弃用整张自定义改键 map，同时停用主机设置的 VID/PID 和蓝牙名称，随后遥控器自动重启并使用固件默认配置。旧覆盖数据仍保留在存储中，不需要卸载或重装 Hook。

仅接受匹配令牌的 `08 44 <token> <status>` 执行回执；状态 0 对应 `outcome=discarded`（弃用状态已保存，等待重启），1 为 `rejected`，2 为 `save_failed`，3 为 `forward_failed`。只有状态 0 返回零退出码。`08 AA` 不是执行成功。超时或发送阶段异常为 `unknown`，不自动重发；发送前失败为 `error`。重启后的连接和按键效果仍需核对。

当前 W306 源码在弃用 map 后再次改键时，以固件出厂表为底，仅写入本次修改，不会带回其他旧改键。
