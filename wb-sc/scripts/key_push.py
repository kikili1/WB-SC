"""遥控器单格键值推送（0x39），用于快速生成并发送改键命令。

报文：05 39 05 <token> <col> <row> <hi> <lo>
回执：0x39 <token> <status>，status 0=已保存 1=参数非法 2=保存失败 3=忙
按键位置按遥控器款式（variant）区分，款式也存在 config.json 里。
"""
import json
import math
import secrets
import sys
import time
from types import SimpleNamespace

import keymap_rc
import receiver_led
from remote_setup import atomic, encode

STATUS_TEXT = {0: 'saved', 1: '参数非法', 2: '保存失败', 3: '忙（恢复出厂中或按键未释放）'}
RESULT_NAMES = ('saved', 'rejected', 'save_failed', 'busy')


def save_variant(name):
    """把款式写进 config.json（安装器会原样保留未知字段，重装后仍在）。"""
    path = receiver_led.config_path()
    config = receiver_led.read_config()
    config.update(variant=name, variant_confirmed=True)
    atomic(path, encode(config))


def find_device(api, args):
    found = receiver_led.candidates(api, SimpleNamespace(
        vid=args.vid, pid=args.pid, path=args.path))
    if len(found) != 1:
        raise ValueError('找到 %d 个接收器；用 `led list` 查看并用 --path 指定' % len(found))
    return found[0]


def wait_ack(read, token, timeout):
    """读取回执里的 status；超时返回 None。"""
    deadline = time.monotonic() + timeout
    while True:
        remain = deadline - time.monotonic()
        if remain <= 0:
            return None
        data = read(remain)
        if not data:
            return None
        if (len(data) >= 17 and data[:3] == bytes((0x08, 0x39, token))
                and data[3] in STATUS_TEXT and not any(data[4:])):
            return data[3]


def resolve_target(args, keys):
    if args.name:
        if args.col is not None or args.row is not None:
            raise ValueError('--name 与 --col/--row 只能二选一')
        item = keys[args.name]
        col, row = item['pos']
        label = '%s C%d/R%d' % (args.name, col, row)
    else:
        if args.col is None or args.row is None:
            raise ValueError('请用 --name，或同时给 --col 与 --row')
        col, row = args.col, args.row
        label = 'C%d/R%d' % (col, row)
        item = None

    if args.restore:
        if item is None:
            raise ValueError('--restore 需要配合 --name')
        return col, row, item['factory'], label
    if not args.key:
        raise ValueError('请用 --key 指定目标键值，或用 --restore 恢复出厂值')
    return col, row, keymap_rc.parse_key(args.key), label


def execute(args):
    result = {}
    attempted = False

    def finish(outcome, message, code, *, error=False):
        if getattr(args, 'json', False):
            print(json.dumps(dict(result, outcome=outcome, message=message)))
        else:
            print(message, file=sys.stderr if error else sys.stdout)
        return code

    try:
        if args.operation == 'use':
            keymap_rc.variant_keys(args.variant)
            save_variant(args.variant)
            print('已记录遥控器款式：%s（已确认）' % args.variant)
            return 0

        config = receiver_led.read_config()
        variant = args.variant or config.get('variant') or keymap_rc.DEFAULT_VARIANT
        keys = keymap_rc.variant_keys(variant)

        if args.operation == 'list':
            print('遥控器款式：%s  （%s）' % (variant, keymap_rc.VARIANTS[variant]['note']))
            confirmed = config.get('variant') == variant and config.get('variant_confirmed') is True
            print('款式确认：%s' % ('已确认' if confirmed else '待确认'))
            for name, item in keys.items():
                col, row = item['pos']
                print('%-8s 逻辑%-2s C%d/R%d  出厂 0x%04X  %-14s %s' % (
                    name, item.get('logical', '?'), col, row, item['factory'],
                    keymap_rc.describe(item['factory']), item['note']))
            return 0

        if not math.isfinite(args.timeout) or not 0 < args.timeout <= 60:
            raise ValueError('超时必须在 0~60 秒之间')
        if args.name and args.name not in keys:
            raise ValueError('款式 %s 未收录按键 %r；可用：%s'
                             % (variant, args.name, '、'.join(keys)))
        confirmed = config.get('variant') == variant and config.get('variant_confirmed') is True
        if args.yes and args.name and not confirmed and not args.allow_unconfirmed:
            raise ValueError('款式 %s 尚未确认，按名字改键可能改到错误的物理键；'
                             '先跑 key use --variant %s 确认，或改用 --col/--row，'
                             '或明确接受风险加 --allow-unconfirmed' % (variant, variant))
        col, row, value, label = resolve_target(args, keys)
        token = secrets.randbelow(256)
        packet = keymap_rc.cell_packet(token, col, row, value)

        result.update(variant=variant, col=col, row=row, value=value, token=token,
                      variant_confirmed=confirmed, tx=packet.hex(' ').upper())
        if not args.json:
            print('%s  %s  目标 0x%04X  %s' % (variant, label, value, keymap_rc.describe(value)))
            print('TX: %s' % result['tx'])
        if not args.yes:
            return finish('preview', '（预览）加 --yes 才会写入遥控器', 0)

        api = receiver_led.native()
        device = find_device(api, args)
        with api.open_reader(device) as read:
            attempted = True
            deadline = time.monotonic() + args.timeout
            api.write_report(device, packet, args.timeout)
            status = wait_ack(read, token, deadline - time.monotonic())
        if status is None:
            return finish('unknown', '已发送，未收到遥控器回执，保存结果未知', 1)
        result['status'] = status
        return finish(RESULT_NAMES[status], 'Remote result: %s' % STATUS_TEXT[status], int(status != 0))
    except (OSError, ValueError) as exc:
        outcome = 'unknown' if attempted else 'error'
        return finish(outcome, 'Key push: %s' % exc, 1, error=True)


def configure(parser):
    sub = parser.add_subparsers(dest='operation', required=True)

    p = sub.add_parser('list', help='列出该款式的键位与出厂键值')
    p.add_argument('--variant', choices=keymap_rc.variant_names(), help='遥控器款式，默认取 config.json')
    p.set_defaults(func=execute)

    p = sub.add_parser('use', help='记录当前遥控器款式')
    p.add_argument('--variant', choices=keymap_rc.variant_names(), required=True)
    p.set_defaults(func=execute)

    p = sub.add_parser('push', help='推送单个键值到指定键位')
    p.add_argument('--variant', choices=keymap_rc.variant_names(), help='遥控器款式，默认取 config.json')
    p.add_argument('--name', help='物理键名，如 K_S1（按款式查表，见 key list）')
    p.add_argument('--col', type=int, help='列号 0~6（与 --name 二选一）')
    p.add_argument('--row', type=int, help='行号 0~8（固件 KEYMAP_ROWS=9）')
    value = p.add_mutually_exclusive_group(required=True)
    value.add_argument('--key', help='目标键值："Alt+Shift+T"、"0x6617"、"F4"')
    value.add_argument('--restore', action='store_true', help='恢复该键的出厂值')
    vid, pid, path = receiver_led.device_defaults()
    p.add_argument('--vid', type=lambda s: int(s, 16), default=vid)
    p.add_argument('--pid', type=lambda s: int(s, 16), default=pid)
    p.add_argument('--path', default=path, help='多设备时用 led list 的完整 path')
    p.add_argument('--timeout', type=float, default=2)
    p.add_argument('--allow-unconfirmed', action='store_true', help='款式未确认也按名字改键')
    p.add_argument('--yes', action='store_true', help='真正写入（否则只打印报文）')
    p.add_argument('--json', action='store_true', help='输出单个 JSON 结果')
    p.set_defaults(func=execute)
