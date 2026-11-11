"""Standalone Windows receiver LED sender; Python standard library only."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

STATES = {"idle": 0, "busy": 1, "done": 2, "error": 3, "wait": 4, "compact": 5}
PROBE = None  # 能力查询报文，见 out_packet()


def config_path():
    """设备配置：安装后在 ~/.workbuddy/wb-sc/config.json，直接跑源码时回落到同目录。"""
    scripts = Path(__file__).resolve().parent
    if scripts.name == 'runtime':
        return scripts.parent / 'config.json'
    installed = Path.home() / '.workbuddy' / 'wb-sc' / 'config.json'
    if installed.exists():
        return installed
    return Path(__file__).resolve().parent.parent / 'config.json'


def read_config():
    try:
        return json.loads(config_path().read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}


def hex_or(value, fallback):
    try:
        number = int(str(value), 16)
    except (TypeError, ValueError):
        return fallback
    return number if 0 <= number <= 0xFFFF else fallback


def device_defaults():
    """让所有命令默认跟随 config.json，用户换接收器只需改一处。"""
    config = read_config()
    return hex_or(config.get('vid'), 0x1915), hex_or(config.get('pid'), 0x1025), config.get('path')


def packet(state):
    return bytes((5, 0x43, 1, STATES[state]))


def out_packet(args):
    if args.operation == 'probe':
        # 用与正式命令完全相同的帧型探能力：旧固件收到会静默丢弃（无回执），
        # 新固件回 43 <state> 0/1。避免依赖 1 字节报文的长度判据。
        return bytes((5, 0x43, 1, STATES['compact']))
    return packet(args.state)


def hex_id(value):
    number = int(value, 16)
    if not 0 <= number <= 65535:
        raise argparse.ArgumentTypeError('VID/PID must fit 16 bits')
    return number


def native():
    if os.name != 'nt':
        raise OSError('Receiver LED control requires Windows')
    import win_hid
    return win_hid


def candidates(api, args, devices=None):
    # W305 系列接收器的厂商集合是 0xFF02，W306 实测为 0xFF01；两者都接受，
    # 仍用 64/17 字节长度和多设备拒绝来避免选错集合。
    if devices is None:
        devices = api.enumerate_hid_devices()
    return [d for d in devices
            if d.vendor_id == args.vid and d.product_id == args.pid
            and d.usage_page in (0xFF01, 0xFF02) and d.output_report_length >= 64
            and d.input_report_length >= 17 and (not args.path or d.path == args.path)]


def read_result(read, args):
    """读回包。经接收器时 0x43 只回固定 08 AA（"已转发"），看不到遥控器自己的回执；
    直连 BLE（无接收器）才能看到 43 <state> <status>。偶发丢包由 execute 重发一次兜底。"""
    if args.operation == 'send':
        token = STATES[args.state]
    else:
        token = STATES['compact']
    deadline = time.monotonic() + args.timeout
    while True:
        remain = deadline - time.monotonic()
        if remain <= 0:
            break
        data = read(remain)
        if not data:
            break
        for i in range(len(data) - 2):
            if data[i] == 0x08 and data[i + 1] == 0xAA:
                return '接收器已转发（08 AA）；实际效果看灯'
            if data[i] != 0x43 or data[i + 1] != token:
                continue
            status = data[i + 2]
            if args.operation == 'probe':
                return ('固件支持 wait/compact（回执 ok）' if status == 0
                        else '固件有回执但拒绝了状态 %d（status %d）' % (token, status))
            return 'Remote result: %s' % ('ok' if status == 0 else 'rejected (%d)' % status)
    if args.operation == 'probe':
        return '无回包：接收器仍过滤状态 4/5（app_dongle.c 的 packet[2] > 3），或遥控器未连上'
    return '已发送，未收到回包'


def execute(args):
    try:
        if not math.isfinite(args.timeout) or not 0 < args.timeout <= 60:
            raise ValueError('Timeout must be between 0 and 60 seconds')
        if os.name != 'nt':
            raise OSError('Receiver LED control requires Windows')
        if args.operation in ('send', 'probe') and not args.yes:
            print('[dry-run] TX:', out_packet(args).hex(' ').upper())
            return 0
        path = args.path
        if args.worker or args.operation == 'list' or not args.no_wait:
            api = native()
            devices = candidates(api, args)
        if args.operation == 'list':
            print(json.dumps([vars(d) for d in devices], ensure_ascii=False, indent=2))
            if not devices:
                print('未匹配到 %04X:%04X 的接收器；先跑 wbsc.py remote doctor 看完整诊断'
                      % (args.vid, args.pid), file=sys.stderr)
            return 0
        if args.worker or not args.no_wait:
            if len(devices) != 1:
                raise ValueError('Expected one receiver, found %d; use led list and --path' % len(devices))
            path = devices[0].path
        if args.worker:
            device = devices[0]
            if args.no_wait:
                api.write_report(device, out_packet(args), args.timeout)
                print('已发送（不等回执）')
            else:
                with api.open_reader(device) as read:
                    api.write_report(device, out_packet(args), args.timeout)
                    print(read_result(read, args))
            return 0
        # A separate process bounds cleanup even if a faulty driver stalls cancellation.
        command = [sys.executable, '-B', str(Path(__file__).resolve()), args.operation]
        if args.operation == 'send':
            command.append(args.state)
        command += ['--yes', '--worker', '--vid', '%04x' % args.vid,
                    '--pid', '%04x' % args.pid,
                    '--timeout', str(args.timeout)]
        if path:
            command += ['--path', path]
        if args.no_wait:
            command.append('--no-wait')
        # 偶发丢包约 1/10（链路噪声，与状态无关）：手动命令重发一次即可，
        # 同状态重发是幂等的；Hook 走 --no-wait，不进这个重试。
        for attempt in range(2):
            result = subprocess.run(command, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=args.timeout + 1,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                raise OSError(result.stderr.strip() or 'HID write failed')
            text = result.stdout.strip()
            if args.no_wait or args.operation != 'send' or attempt or '回包' not in text:
                break
        print(text)
        if args.operation == 'probe' and ('固件支持' in text or '08 AA' in text):
            # 能力查询用 compact 帧，会把灯留在紫色呼吸；探测完必须还原。
            idle = argparse.Namespace(**dict(vars(args), operation='send', state='idle'))
            try:
                execute(idle)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print('Receiver LED: %s' % exc, file=sys.stderr)
        return 1


def configure(parser):
    sub = parser.add_subparsers(dest='operation', required=True)
    vid, pid, path = device_defaults()
    for operation in ('list', 'send', 'probe'):
        p = sub.add_parser(operation)
        if operation == 'send':
            p.add_argument('state', choices=STATES)
        p.add_argument('--vid', type=hex_id, default=vid)
        p.add_argument('--pid', type=hex_id, default=pid)
        p.add_argument('--path', default=path)
        p.add_argument('--timeout', type=float, default=2)
        p.add_argument('--yes', action='store_true')
        p.add_argument('--no-wait', action='store_true',
                       help='只写 USB，不等 0x43 回执（Hook 用，避免拖慢每条消息）')
        p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
        p.set_defaults(func=execute)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    configure(parser)
    args = parser.parse_args(argv)
    return execute(args)


if __name__ == '__main__':
    sys.exit(main())
