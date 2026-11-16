"""Install only WB-SC-owned command hooks; preserve all other host settings."""
import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid

import hook_profiles

VERSION = '0.6.1'
FILES = ('receiver_led.py', 'win_hid.py', 'status_hook.py', 'run.ps1', 'hook_profiles.py')
MAC_FILES = ('receiver_led.py', 'mac_hid.py', 'status_hook.py', 'hook_profiles.py')


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
    list(hook_profiles.entries(settings))
    hooks = settings.get('hooks', {})
    for event, groups in list(hooks.items()):
        kept = []
        for group in groups:
            if 'hooks' in group:
                rest = [h for h in group['hooks'] if hook_profiles.command_of(h) not in commands]
                if len(rest) == len(group['hooks']):
                    kept.append(group)
                elif rest:
                    kept.append(dict(group, hooks=rest))
            elif hook_profiles.command_of(group) not in commands:
                kept.append(group)
        if kept:
            hooks[event] = kept
        elif groups:
            hooks.pop(event, None)
    if not hooks:
        settings.pop('hooks', None)
    return settings


def paths(home, agent='workbuddy', hook_file=None):
    return hook_profiles.paths(home, agent, hook_file)


def hook_command(root, python=None, arguments=()):
    if sys.platform == 'darwin':
        if python is None:
            python = sys.executable
        return shlex.join([str(python), '-B', str(root / 'runtime/status_hook.py'), *arguments])
    if python is None:
        return ('powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden '
                '-ExecutionPolicy Bypass -File "%s"' % (root / 'runtime/run.ps1'))
    exe = Path(python).as_posix()
    script = (root / 'runtime/status_hook.py').as_posix()
    # A bare executable works in both WorkBuddy shells. The encoded fallback
    # preserves literal paths when the executable needs shell-specific quoting.
    if re.fullmatch(r'[A-Za-z]:/[A-Za-z0-9_./-]+', exe) and not any(c in script for c in '$`"'):
        return ('%s -B "%s"' % (exe, script)) + ''.join(' ' + a for a in arguments)
    invocation = "& '%s' -B '%s'" % (exe.replace("'", "''"), script.replace("'", "''"))
    invocation += ''.join(" '%s'" % a.replace("'", "''") for a in arguments)
    encoded = base64.b64encode(invocation.encode('utf-16-le')).decode('ascii')
    return 'powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ' + encoded


def usable_python(path):
    if not path or not Path(path).is_absolute() or not Path(path).is_file():
        return False
    try:
        check = ('import sys; import hid; assert hasattr(hid.device, "get_report_descriptor"); '
                 'sys.exit(sys.version_info < (3, 10))' if sys.platform == 'darwin' else
                 'import sys; sys.exit(sys.version_info < (3, 8))')
        result = subprocess.run([path, '-B', '-c', check],
                                capture_output=True, timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def select_python(home):
    pattern = '*/bin/python3' if sys.platform == 'darwin' else '*/python.exe'
    managed = (home / '.workbuddy/binaries/python/versions').glob(pattern)
    for path in [*sorted(managed, key=lambda p: p.stat().st_mtime, reverse=True), Path(sys.executable)]:
        if usable_python(str(path)):
            return str(path)
    raise OSError('No usable Hook Python; macOS needs Python 3.10+ with hidapi==0.15.0 '
                  '(install using the selected Python -m pip install hidapi==0.15.0); Windows needs 3.8+')


def runtime_files():
    return MAC_FILES if sys.platform == 'darwin' else FILES


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError('Device configuration must be an object')
    for key in ('vid', 'pid'):
        if not 0 <= int(config[key], 16) <= 65535:
            raise ValueError('Invalid receiver VID/PID')
    if config.get('path') is not None and not isinstance(config['path'], str):
        raise ValueError('Receiver path must be a string or null')


def activation_note(agent):
    return {
        'codex': '配置检查不代表生效：在 Codex /hooks 中审核并信任当前定义。',
        'trae': '配置检查不代表生效：在宿主 Hooks 设置中启用，确认运行方式；避免重复导入 Claude Hooks。',
        'deepseek': '配置检查不代表生效：将官方 dsh-hooks-claude-code 桥挂载到当前 composition，并令 configPath 指向此文件。',
        'copilot-local': '配置检查不代表生效：确认 VS Code Local 会话启用 chat.useHooks 且工作区受信任。',
        'copilot': '配置检查不代表生效：确认本地会话实际使用 Copilot 运行时，非云端执行。',
    }.get(agent)


def inspect(home=None, source=None, agent='workbuddy', hook_file=None):
    """安装状态快照，status 与 doctor 共用。"""
    home = Path.home() if home is None else Path(home)
    settings_path, root = paths(home, agent, hook_file)
    manifest_path = root / 'installed.json'
    settings = load(settings_path, {}) if settings_path.exists() else {}
    manifest = load(manifest_path, {}) if manifest_path.exists() else {}
    if not isinstance(settings, dict) or not isinstance(manifest, dict):
        raise ValueError('Host settings and installation record must be objects')
    if manifest and manifest.get('agent', 'workbuddy') != agent:
        raise ValueError('This runtime directory belongs to another host; select a separate --hook-file')
    source = Path(__file__).resolve().parent if source is None else Path(source)
    python = manifest.get('python')
    command = hook_command(root, python)
    owned = {command, hook_command(root), *manifest.get('commands', [])}
    expected = hook_profiles.registrations(agent, lambda args: hook_command(root, python, args))
    owned.update(hook_profiles.command_of(h) for _, _, h in hook_profiles.entries({'hooks': expected}))
    actual = {}
    for event, group, handler in hook_profiles.entries(settings):
        if hook_profiles.command_of(handler) in owned:
            actual.setdefault(event, []).append((group.get('matcher'), handler))
    wanted = {}
    for event, group, handler in hook_profiles.entries({'hooks': expected}):
        wanted.setdefault(event, []).append((group.get('matcher'), handler))
    events = list(actual)
    registered = actual == wanted
    if agent in ('cursor', 'copilot', 'copilot-local', 'trae'):
        registered = registered and settings.get('version') == 1
    intact = all((root / 'runtime' / f).is_file() and
                 hashlib.sha256((root / 'runtime' / f).read_bytes()).hexdigest() == manifest.get('hashes', {}).get(f)
                 for f in runtime_files())
    current = manifest.get('version') == VERSION and all(
        hashlib.sha256((source / f).read_bytes()).hexdigest() == manifest.get('hashes', {}).get(f)
        for f in runtime_files()) and manifest.get('platform', 'win32') == sys.platform \
        and manifest.get('agent', 'workbuddy') == agent
    python_ready = usable_python(python)
    config_path = root / 'config.json'
    try:
        validate_config(load(config_path, {}))
        config_ready = True
    except (OSError, KeyError, TypeError, ValueError):
        config_ready = False
    return {'agent': agent, 'settings': str(settings_path),
            'activation_required': activation_note(agent),
            'version': manifest.get('version'), 'runtime_intact': intact, 'events': events,
            'registered': registered, 'current': current, 'python': python, 'python_ready': python_ready,
            'config_ready': config_ready,
            'ready': registered and intact and current and python_ready and config_ready,
            'root': root, 'config': config_path}


def operate(action, yes=False, home=None, source=None, agent='workbuddy', hook_file=None):
    home = Path.home() if home is None else Path(home)
    source = Path(__file__).resolve().parent if source is None else Path(source)
    if action == 'status':
        result = inspect(home, source, agent, hook_file)
        print(json.dumps({k: str(v) if k == 'config' else v for k, v in result.items() if k != 'root'},
                         ensure_ascii=False, indent=2))
        return result
    if action == 'doctor':
        return doctor(home, probe=yes, agent=agent, hook_file=hook_file)
    settings_path, root = paths(home, agent, hook_file)
    manifest_path = root / 'installed.json'
    settings_before = settings_path.read_bytes() if settings_path.exists() else None
    settings = json.loads(settings_before.decode('utf-8-sig')) if settings_before is not None else {}
    if not isinstance(settings, dict):
        raise ValueError('Host settings must be a JSON object')
    manifest = load(manifest_path, {})
    if not isinstance(manifest, dict):
        raise ValueError('Invalid WB-SC installation record')
    if manifest and manifest.get('agent', 'workbuddy') != agent:
        raise ValueError('This runtime directory belongs to another host; select a separate --hook-file')
    managed = {hook_command(root), hook_command(root, manifest.get('python')), *manifest.get('commands', [])}
    if action == 'install':
        if sys.platform not in ('win32', 'darwin'):
            raise OSError('WB-SC receiver hooks support Windows and macOS only')
        if agent == 'workbuddy' and any(v for k, v in settings.get('enabledPlugins', {}).items() if k.startswith('workbuddy-status-led@')):
            raise ValueError('Disable the old workbuddy-status-led plugin first to avoid duplicate hooks')
        # 款式默认 HM-AItest-1，但未确认：别人拿到的可能是别的排布，
        # 未确认时 key push --name 会拒绝，避免照着样机位置改错键。
        config_path = root / 'config.json'
        config = load(config_path, {}) if config_path.exists() else load(
            home / '.workbuddy/wb-sc/config.json',
            {'vid': '1915', 'pid': '1025', 'path': None,
             'variant': 'HM-AItest-1', 'variant_confirmed': False})
        validate_config(config)
        if inspect(home, source, agent, hook_file)['ready']:
            print('WB-SC hooks already current. Receiver config: %s' % config_path)
            return
        python = select_python(home)
        registrations = hook_profiles.registrations(agent, lambda args: hook_command(root, python, args))
        managed.update(hook_profiles.command_of(h) for _, _, h in hook_profiles.entries({'hooks': registrations}))
        payload = {root / 'runtime' / f: (source / f).read_bytes() for f in runtime_files()}
        for name, digest in manifest.get('hashes', {}).items():
            if name in FILES + MAC_FILES and name not in runtime_files():
                old = root / 'runtime' / name
                if old.is_file() and hashlib.sha256(old.read_bytes()).hexdigest() == digest:
                    payload[old] = None
        if not config_path.exists():
            payload[config_path] = encode(config)
        settings = without_owned(settings, managed)
        if agent in ('cursor', 'copilot', 'copilot-local', 'trae'):
            if settings.get('version', 1) != 1:
                raise ValueError('Unsupported hook configuration version')
            settings['version'] = 1
        for event, groups in registrations.items():
            settings.setdefault('hooks', {}).setdefault(event, []).extend(groups)
        payload[manifest_path] = encode({'version': VERSION, 'platform': sys.platform,
            'agent': agent, 'commands': sorted(managed), 'python': python,
            'hashes': {f: hashlib.sha256(payload[root / 'runtime' / f]).hexdigest() for f in runtime_files()}})
    else:
        settings = without_owned(settings, managed)
        payload = {manifest_path: None}
        residual = (root / 'runtime').as_posix().casefold() in json.dumps(
            settings.get('hooks', {}), ensure_ascii=False).replace('\\\\', '/').casefold()
        for f, digest in manifest.get('hashes', {}).items():
            if f not in FILES + MAC_FILES:
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
                raise OSError('Host settings changed during installation; retry')
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
    print('%s completed for %s. Receiver config: %s' % (action, agent, root / 'config.json'))
    if action == 'install' and activation_note(agent):
        print(activation_note(agent))


def doctor(home=None, probe=False, agent='workbuddy', hook_file=None):
    """逐项自检，输出 ok/warn/fail 与下一步。其他用户拿到设备先跑这一条。"""
    from types import SimpleNamespace

    home = Path.home() if home is None else Path(home)
    failures = []

    def say(tag, text):
        print('[%s] %s' % (tag, text))
        if tag == 'fail':
            failures.append(text)

    supported = sys.platform == 'darwin' or os.name == 'nt'
    say('ok' if supported else 'fail', '平台：%s（支持 Windows/macOS）' % sys.platform)

    state = inspect(home, agent=agent, hook_file=hook_file)
    hook_python = state['python']
    if not state['python_ready']:
        try:
            hook_python = select_python(home)
        except OSError:
            hook_python = None
    say('ok' if hook_python else 'fail',
        '可用的 Hook Python：%s' % (hook_python or '未找到；Mac 需要 Python 3.10+ 和 hidapi==0.15.0'))
    required = (3, 10) if sys.platform == 'darwin' else (3, 8)
    say('ok' if sys.version_info >= required else 'fail', '当前 Python：%s' % sys.version.split()[0])
    if sys.platform == 'darwin':
        say('ok' if hook_python else 'fail', 'HIDAPI：随 Hook Python 检查；缺失时用该 Python -m pip install hidapi==0.15.0')

    if state['ready']:
        say('ok', 'Hook 已安装：版本 %s，%d/%d 事件' % (state['version'], len(state['events']), len(hook_profiles.PROFILES[agent][1])))
    elif state['version']:
        say('warn', 'Hook 版本 %s，事件 %d/%d；建议重跑 remote install --yes'
            % (state['version'], len(state['events']), len(hook_profiles.PROFILES[agent][1])))
    else:
        say('warn', 'Hook 未安装：跑 remote install --yes')

    if state['activation_required']:
        say('warn', state['activation_required'])

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

    if not supported:
        return 1

    import receiver_led
    args = SimpleNamespace(vid=int(vid, 16), pid=int(pid, 16), path=config.get('path'))
    try:
        api = receiver_led.native()
        devices = api.enumerate_hid_devices()
    except (OSError, ValueError) as exc:
        say('fail', 'HID 枚举/打开失败：%s' % exc)
        return 1
    matched = receiver_led.candidates(api, args, devices=devices)
    if len(matched) == 1:
        d = matched[0]
        try:
            with api.open_reader(d):
                pass
        except OSError as exc:
            say('fail', '无法打开接收器：%s；按实际系统错误检查设备访问权限' % exc)
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
        result = operate(args.action, args.yes, agent=args.agent, hook_file=args.hook_file)
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
        p.add_argument('--agent', choices=tuple(hook_profiles.PROFILES), default='workbuddy',
                       help='由当前 agent 按 skill 选择；省略仅兼容旧 WorkBuddy 调用')
        p.add_argument('--hook-file', type=Path, help='当前宿主实际使用的 Hook 文件')
        p.add_argument('--yes', action='store_true')
        p.set_defaults(func=execute)
    return sub


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    configure(parser)
    sys.exit(execute(parser.parse_args()))
