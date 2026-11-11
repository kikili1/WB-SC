"""遥控器厂商信息查询：让遥控器上报一次 CS 号 / 版本 / RSSI / 名称。

报文格式取自产测上位机 dongle_host_core/decoder.py（权威实现）：
  主机 -> 接收器（HID 输出，report id 0x04）
      04 1F 00 00 00 00 00 00 72        请求遥控器信息（0x1F）
  遥控器 -> 主机（HID 输入，report id 0x08，载荷从第二个字节开始）
      08 18 <len> <cs 字节，低字节在前>  CS 号
      08 13 <len> <text>                版本分片
      08 12 <..> <ascii rssi>           信号强度
      08 10 / 08 11 <..> <text>         本机名 / 遥控器名
      08 1F                            查询确认

当前 W306 固件只有 0x43/0x39/0x3x 一套命令，尚未实现 0x1F 查询，
因此本模块只负责"问了就听、听不到就如实说"，不回包时不影响其他功能。
固件放行后无需改动主机侧。
"""
QUERY = bytes.fromhex('04 1F 00 00 00 00 00 00 72')
REPORT_ID = 0x08

NAMES = {
    0x10: 'local-name', 0x11: 'remote-name', 0x12: 'rssi',
    0x13: 'version', 0x18: 'cs', 0x1F: 'query-ack',
}


def decode(data):
    """把一条 17 字节输入报告解成 (kind, text)；不认识返回 None。"""
    raw = bytes(data)
    if not raw or raw[0] != REPORT_ID or len(raw) < 3:
        return None
    payload = raw[1:]
    message = payload[0]
    if message == 0x18:
        length = payload[1]
        if length <= 0 or len(payload) < 2 + length:
            return None
        # 遥控器按低字节在前存，上位机按字节倒序转十六进制
        return 'cs', payload[2:2 + length][::-1].hex().upper()
    if message == 0x1F:
        return 'query-ack', ''
    if message in (0x10, 0x11, 0x12, 0x13):
        # 0x11 用 1 字节长度 + 1 字节偏移；其余用 2 字节长度
        if len(payload) < 4:
            return None
        length = payload[1] if message == 0x11 else payload[1] | (payload[2] << 8)
        value = payload[3:3 + max(0, min(length, len(payload) - 3))]
        if not value:
            return None
        if message == 0x12:
            return 'rssi', value.rstrip(b'\x00').decode('ascii', 'replace').strip()
        text = value.rstrip(b'\x00').decode('utf-8' if message in (0x10, 0x11) else 'ascii', 'replace')
        return NAMES[message], text.strip()


def collect(api, device, seconds):
    """发送一次查询并收集回包，返回 {kind: text 或 [分片]}。"""
    import time
    found = {}
    version = []
    with api.open_reader(device) as read:
        api.write_report(device, QUERY, min(2.0, max(0.5, seconds)))
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            data = read(min(0.3, remaining))
            if not data:
                continue
            item = decode(data)
            if not item:
                if len(found.get('raw', [])) < 6:
                    found.setdefault('raw', []).append(bytes(data).rstrip(b'\x00').hex(' ').upper())
                continue
            kind, text = item
            if kind == 'version':
                version.append(text)
            else:
                found[kind] = text
    if version:
        found['version'] = ''.join(version)
    return found


def execute(args):
    import math
    import os
    from types import SimpleNamespace
    import receiver_led

    try:
        if not math.isfinite(args.seconds) or not 0 < args.seconds <= 30:
            raise ValueError('--seconds 必须在 0~30 之间')
        print('查询遥控器信息：TX %s' % QUERY.hex(' ').upper())
        if not args.yes:
            print('（预览）加 --yes 才会真正发送并等待回包')
            return 0
        if os.name != 'nt':
            raise OSError('遥控器信息查询需要 Windows')
        api = receiver_led.native()
        devices = receiver_led.candidates(api, SimpleNamespace(
            vid=args.vid, pid=args.pid, path=args.path))
        if len(devices) != 1:
            raise ValueError('找到 %d 个接收器；用 led list 查看并用 --path 指定' % len(devices))
        found = collect(api, devices[0], args.seconds)

        labels = (('cs', 'CS 号'), ('version', '版本'), ('rssi', 'RSSI'),
                  ('local-name', '本机名'), ('remote-name', '遥控器名'))
        for key, label in labels:
            if found.get(key):
                print('%-8s %s' % (label + ':', found[key]))
        if 'query-ack' in found:
            print('查询确认: 已确认')
        for line in found.get('raw', [])[:6]:
            print('其它回包: %s' % line)
        if any(found.get(k) for k in ('cs', 'version')):
            return 0
        print()
        print('未收到 CS 号/版本回包（等待 %.1f 秒）。' % args.seconds)
        print('先跑 `led probe --yes` 确认链路在线；若只回 08 AA，说明当前固件未实现 0x1F 查询。')
        print('固件放行 0x1F 请求与 0x18 CS 上报后，本命令无需修改即可读到 CS 号。')
        return 1
    except (OSError, ValueError) as exc:
        print('Remote info: %s' % exc, file=__import__('sys').stderr)
        return 1


def configure(sub, defaults):
    """挂到 remote 子命令下：remote info。"""
    p = sub.add_parser('info', help='向遥控器查询一次 CS 号/版本（需固件支持 0x1F）')
    p.add_argument('--vid', type=lambda s: int(s, 16), default=defaults[0])
    p.add_argument('--pid', type=lambda s: int(s, 16), default=defaults[1])
    p.add_argument('--path', default=defaults[2])
    p.add_argument('--seconds', type=float, default=3, help='等待回包秒数，默认 3')
    p.add_argument('--yes', action='store_true', help='真正发送（否则只打印报文）')
    p.set_defaults(func=execute)
    return p
