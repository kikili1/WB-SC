"""Install only WB-SC-owned command hooks; preserve all other WorkBuddy settings."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

VERSION = '0.4.0'
FILES = ('receiver_led.py', 'win_hid.py', 'status_hook.py', 'run.ps1')
EVENTS = ('SessionStart', 'UserPromptSubmit', 'Stop', 'StopFailure',
          'PermissionRequest', 'Notification', 'PreCompact', 'SessionEnd')


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def load(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def without_owned(settings, commands):
    hooks = settings.get('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Existing hooks must be an object')
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            raise ValueError('Existing event hooks must be arrays')
        kept = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get('hooks', []), list):
                raise ValueError('Invalid existing hook group')
            entries = group.get('hooks', [])
            rest = [h for h in entries if not (isinstance(h, dict) and h.get('type') == 'command'
                                              and h.get('command') in commands)]
            if len(rest) == len(entries):
                kept.append(group)
            elif rest:
                kept.append(dict(group, hooks=rest))
        if kept:
            hooks[event] = kept
        elif groups:
            hooks.pop(event, None)
    if not hooks:
        settings.pop('hooks', None)
    return settings


def paths(home):
    base = home / '.workbuddy'
    return base / 'settings.json', base / 'wb-sc'


def hook_command(root, python=None):
    if python is None:
        return ('powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden '
                '-ExecutionPolicy Bypass -File "%s"' % (root / 'runtime/run.ps1'))
    exe = Path(python).as_posix()
    script = (root / 'runtime/status_hook.py').as_posix()
    # A bare executable works in both WorkBuddy shells. The encoded fallback
    # preserves literal paths when the executable needs shell-specific quoting.
    if re.fullmatch(r'[A-Za-z]:/[A-Za-z0-9_./-]+', exe) and not any(c in script for c in '$`"'):
        return '%s -B "%s"' % (exe, script)
    invocation = "& '%s' -B '%s'" % (exe.replace("'", "''"), script.replace("'", "''"))
    encoded = base64.b64encode(invocation.encode('utf-16-le')).decode('ascii')
    return 'powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ' + encoded


def usable_python(path):
    if not path or not Path(path).is_absolute() or not Path(path).is_file():
        return False
    try:
        result = subprocess.run([path, '-B', '-c', 'import sys; sys.exit(sys.version_info < (3, 8))'],
                                capture_output=True, timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def select_python(home):
    managed = (home / '.workbuddy/binaries/python/versions').glob('*/python.exe')
    for path in [*sorted(managed, key=lambda p: p.stat().st_mtime, reverse=True), Path(sys.executable)]:
        if usable_python(str(path)):
            return str(path)
    raise OSError('No usable Python 3.8+ interpreter for WB-SC hooks')


def validate_config(config):
    for key in ('vid', 'pid'):
        if not 0 <= int(config[key], 16) <= 65535:
            raise ValueError('Invalid receiver VID/PID')
    if config.get('path') is not None and not isinstance(config['path'], str):
        raise ValueError('Receiver path must be a string or null')


def inspect(home=None, source=None):
    """安装状态快照，status 与 doctor 共用。"""
    home = Path.home() if home is None else Path(home)
    settings_path, root = paths(home)
    manifest_path = root / 'installed.json'
    settings = load(settings_path, {}) if settings_path.exists() else {}
    manifest = load(manifest_path, {}) if manifest_path.exists() else {}
    source = Path(__file__).resolve().parent if source is None else Path(source)
    python = manifest.get('python')
    command = hook_command(root, python)
    owned = {command, hook_command(root)}
    entries = {event: [(g.get('matcher'), h) for g in groups for h in g.get('hooks', [])
                       if isinstance(h, dict) and h.get('type') == 'command' and h.get('command') in owned]
               for event, groups in settings.get('hooks', {}).items()}
    events = [event for event, matches in entries.items() if matches]
    expected = (None, {'type': 'command', 'command': command, 'timeout': 6})
    registered = all(entries.get(event) == [expected] for event in EVENTS) and set(events) == set(EVENTS)
    intact = all((root / 'runtime' / f).is_file() and
                 hashlib.sha256((root / 'runtime' / f).read_bytes()).hexdigest() == manifest.get('hashes', {}).get(f)
                 for f in FILES)
    current = manifest.get('version') == VERSION and all(
        hashlib.sha256((source / f).read_bytes()).hexdigest() == manifest.get('hashes', {}).get(f)
        for f in FILES)
    python_ready = usable_python(python)
    config_path = root / 'config.json'
    try:
        validate_config(load(config_path, {}))
        config_ready = True
    except (OSError, KeyError, TypeError, ValueError):
        config_ready = False
    return {'version': manifest.get('version'), 'runtime_intact': intact, 'events': events,
            'registered': registered, 'current': current, 'python_ready': python_ready,
            'config_ready': config_ready,
            'ready': registered and intact and current and python_ready and config_ready,
            'root': root, 'config': config_path}


def check_events_in_sync():
    """Hook 条目与事件映射必须一一对应，否则事件会被静默忽略。"""
    import status_hook
    missing = set(EVENTS) - set(status_hook.EVENTS)
    extra = set(status_hook.EVENTS) - set(EVENTS)
    if missing or extra:
        raise ValueError('EVENTS 与 status_hook 不一致：缺 %s，多 %s' % (sorted(missing), sorted(extra)))


def operate(action, yes=False, home=None, source=None):
    home = Path.home() if home is None else Path(home)
    source = Path(__file__).resolve().parent if source is None else Path(source)
    settings_path, root = paths(home)
    manifest_path = root / 'installed.json'
    settings_before = settings_path.read_bytes() if settings_path.exists() else None
    settings = json.loads(settings_before.decode('utf-8-sig')) if settings_before is not None else {}
    if not isinstance(settings, dict):
        raise ValueError('WorkBuddy settings must be a JSON object')
    manifest = load(manifest_path, {})
    if not isinstance(manifest, dict):
        raise ValueError('Invalid WB-SC installation record')
    managed = {hook_command(root), hook_command(root, manifest.get('python'))}
    if action == 'status':
        result = inspect(home, source)
        print(json.dumps({k: v for k, v in result.items() if k not in ('root', 'config')},
                         ensure_ascii=False, indent=2))
        return result
    if action == 'doctor':
        return doctor(home, probe=yes)
    if action == 'install':
        if os.name != 'nt':
            raise OSError('WB-SC receiver hooks require Windows')
        if any(v for k, v in settings.get('enabledPlugins', {}).items() if k.startswith('workbuddy-status-led@')):
            raise ValueError('Disable the old workbuddy-status-led plugin first to avoid duplicate hooks')
        check_events_in_sync()
        # 款式默认 HM-AItest-1，但未确认：别人拿到的可能是别的排布，
        # 未确认时 key push --name 会拒绝，避免照着样机位置改错键。
        config_path = root / 'config.json'
        config = load(config_path,
                      {'vid': '1915', 'pid': '1025', 'path': None,
                       'variant': 'HM-AItest-1', 'variant_confirmed': False})
        validate_config(config)
        if inspect(home, source)['ready']:
            print('WB-SC hooks already current. Receiver config: %s' % config_path)
            return
        python = select_python(home)
        command = hook_command(root, python)
        managed.add(command)
        payload = {root / 'runtime' / f: (source / f).read_bytes() for f in FILES}
        if not config_path.exists():
            payload[config_path] = encode(config)
        settings = without_owned(settings, managed)
        for event in EVENTS:
            settings.setdefault('hooks', {}).setdefault(event, []).append(
                {'hooks': [{'type': 'command', 'command': command, 'timeout': 6}]})
        payload[manifest_path] = encode({'version': VERSION, 'commands': [command], 'python': python,
            'hashes': {f: hashlib.sha256(payload[root / 'runtime' / f]).hexdigest() for f in FILES}})
    else:
        settings = without_owned(settings, managed)
        payload = {manifest_path: None}
        residual = (root / 'runtime').as_posix().casefold() in json.dumps(
            settings.get('hooks', {}), ensure_ascii=False).replace('\\\\', '/').casefold()
        for f, digest in manifest.get('hashes', {}).items():
            if f not in FILES:
                continue
            path = root / 'runtime' / f
            if path.exists() and not residual and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                payload[path] = None
            elif path.exists():
                print('Preserved modified runtime file:', f)
    payload[settings_path] = encode(settings)
    if not yes:
        print('[dry-run] %s WB-SC hooks at %s; append --yes to apply' % (action, settings_path))
        return
    snapshots = {p: p.read_bytes() if p.exists() else None for p in payload if p != settings_path}
    snapshots[settings_path] = settings_before
    if snapshots[settings_path] is not None:
        backup = root / 'backups' / ('settings-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8] + '.json')
        atomic(backup, snapshots[settings_path])
    done = []
    try:
        for path, data in payload.items():
            if path == settings_path and (path.read_bytes() if path.exists() else None) != settings_before:
                raise OSError('WorkBuddy settings changed during installation; retry')
            if data is None:
                path.unlink(missing_ok=True)
            else:
                atomic(path, data)
            done.append(path)
    except Exception:
        for path in reversed(done):
            if snapshots[path] is None:
                path.unlink(missing_ok=True)
            else:
                atomic(path, snapshots[path])
        raise
    print('%s completed. Receiver config: %s' % (action, root / 'config.json'))


def doctor(home=None, probe=False):
    """逐项自检，输出 ok/warn/fail 与下一步。其他用户拿到设备先跑这一条。"""
    from types import SimpleNamespace

    home = Path.home() if home is None else Path(home)
    failures = []

    def say(tag, text):
        print('[%s] %s' % (tag, text))
        if tag == 'fail':
            failures.append(text)

    windows = os.name == 'nt'
    say('ok' if windows else 'fail', '平台：%s（接收器与 Hook 仅支持 Windows）' % sys.platform)

    state = inspect(home)
    hook_python = load(state['root'] / 'installed.json', {}).get('python')
    if not state['python_ready']:
        try:
            hook_python = select_python(home)
        except OSError:
            hook_python = None
    say('ok' if hook_python else 'fail',
        '可用的 Hook Python：%s' % (hook_python or '未找到可执行的 Python 3.8+'))
    say('ok' if sys.version_info >= (3, 8) else 'fail', '当前 Python：%s' % sys.version.split()[0])

    if state['ready']:
        say('ok', 'Hook 已安装：版本 %s，%d/%d 事件' % (state['version'], len(state['events']), len(EVENTS)))
    elif state['version']:
        say('warn', 'Hook 版本 %s，事件 %d/%d；建议重跑 remote install --yes'
            % (state['version'], len(state['events']), len(EVENTS)))
    else:
        say('warn', 'Hook 未安装：跑 remote install --yes')

    config = {}
    try:
        config = json.loads(state['config'].read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        say('warn', '设备配置不存在（%s）；默认 1915:1025' % state['config'])
    vid = str(config.get('vid') or '1915')
    pid = str(config.get('pid') or '1025')
    variant = config.get('variant')
    if not variant:
        say('warn', '遥控器款式未记录；改键前先 key use --variant <款式>')
    elif config.get('variant_confirmed') is True:
        say('ok', '遥控器款式：%s（已确认）' % variant)
    else:
        say('warn', '遥控器款式 %s 未确认；key push --name 会被拒绝，确认后用 key use --variant %s'
            % (variant, variant))

    if not windows:
        return 1

    import receiver_led
    api = receiver_led.native()
    args = SimpleNamespace(vid=int(vid, 16), pid=int(pid, 16), path=config.get('path'))
    devices = api.enumerate_hid_devices()
    matched = receiver_led.candidates(api, args, devices=devices)
    if len(matched) == 1:
        d = matched[0]
        say('ok', '接收器：%04X:%04X usage_page=0x%02X in/out=%d/%d'
            % (d.vendor_id, d.product_id, d.usage_page, d.input_report_length, d.output_report_length))
    elif matched:
        say('warn', '匹配到 %d 台接收器；在 config.json 的 path 里指定一台（用 led list 复制完整路径）' % len(matched))
    else:
        same_id = [d for d in devices if d.vendor_id == args.vid and d.product_id == args.pid]
        others = [d for d in devices if d.usage_page >= 0xFF00]
        say('fail', '未找到 %s:%s 的接收器（厂商 HID 设备 %d 个）' % (vid, pid, len(others)))
        for d in same_id:
            say('info', '  同 VID/PID 但集合不符：usage_page=0x%02X in/out=%d/%d（脚本接受 0xFF01/0xFF02 且 out>=64）'
                % (d.usage_page, d.input_report_length, d.output_report_length))
        for d in [x for x in others if x not in same_id][:6]:
            say('info', '  候选 %04X:%04X usage_page=0x%02X in/out=%d/%d' %
                (d.vendor_id, d.product_id, d.usage_page, d.input_report_length, d.output_report_length))
        if others:
            say('info', '若上面某一行是接收器，把它的 VID/PID 写进 %s' % state['config'])

    if len(matched) == 1 and probe:
        def led(*argv):
            cmd = [sys.executable, '-B', receiver_led.__file__] + list(argv) + [
                '--yes', '--vid', '%04x' % int(vid, 16), '--pid', '%04x' % int(pid, 16)]
            if config.get('path'):
                cmd += ['--path', config['path']]
            return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', timeout=20).stdout.strip()

        # 探两个端点状态：1（busy）与 5（compact）。经接收器一律回 08 AA（已转发），
        # 偶发丢包，因此判据放宽到“任一条有回包”，并在无回包时重试一次。
        for _ in range(2):
            high = led('probe')
            low = led('send', 'busy')
            if '固件支持' in high or '08 AA' in high or '08 AA' in low or '已转发' in low:
                break
        if '固件支持' in high:
            say('ok', '固件：遥控器回执确认支持状态 0~5（直连 BLE 路径）')
        elif '拒绝了' in high:
            say('fail', '固件有回包但拒绝状态 5：%s' % high)
        elif any('08 AA' in x or '已转发' in x for x in (high, low)):
            say('ok', '接收器已转发 0x43（回 08 AA）；此路径读不到遥控器固件版本，以实际灯效为准')
            say('info', '若 wait/compact 不亮，是接收器固件过滤了 packet[2] > 3，需放行到 <= 5')
        else:
            say('fail', '未收到 0x43 回包：遥控器可能未开机/未连上接收器，或固件早于本版本')
        led('send', 'idle')
    elif len(matched) == 1:
        say('info', '固件探测会点灯；用 remote doctor --yes 实测')

    print()
    if failures:
        print('结论：%d 项未通过，先按上面 fail 项处理。' % len(failures))
        return 1
    print('结论：已执行的检查通过。')
    return 0


def execute(args):
    try:
        result = operate(args.action, args.yes)
        return result if isinstance(result, int) else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print('WB-SC setup: %s' % exc, file=sys.stderr)
        return 1


def configure(parser):
    """返回 remote 的子命令构造器，其他模块（如 remote info）可继续往上挂。"""
    sub = parser.add_subparsers(dest='action', required=True)
    for name, help_text in (('install', '安装/升级状态 Hook 与运行副本'),
                            ('status', '查看安装状态'),
                            ('doctor', '逐项自检：平台/Python/Hook/款式/接收器/固件'),
                            ('uninstall', '卸载本安装器写入的 Hook 与脚本')):
        p = sub.add_parser(name, help=help_text)
        p.add_argument('--yes', action='store_true')
        p.set_defaults(func=execute)
    return sub


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    configure(parser)
    sys.exit(execute(parser.parse_args()))
