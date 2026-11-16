"""Installed command Hook. Never blocks the user's prompt on device failure."""
from contextlib import redirect_stdout
from io import StringIO
import argparse
import json
import sys
import receiver_led
import hook_profiles

def main(argv=()):
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', choices=tuple(hook_profiles.PROFILES), default='workbuddy')
    parser.add_argument('--event')
    options = parser.parse_args(argv)
    try:
        return run(options)
    finally:
        if options.agent != 'workbuddy':
            print('{}')


def run(options):
    try:
        data = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError('Hook input exceeds 1 MiB')
        event = json.loads(data.decode('utf-8-sig'))
        if not isinstance(event, dict):
            raise ValueError('Hook input must be a JSON object')
        name = options.event or event.get('hook_event_name')
        if options.event and event.get('hook_event_name', name) != name:
            raise ValueError('Hook event does not match registration')
        state = hook_profiles.state_for(options.agent, name, event)
        if state is None:
            return 0
        # shortcut: latest session wins; aggregate if concurrent chats must share one LED.
        # 安装运行副本从所在目录读取设备配置。
        config = receiver_led.read_config()
        if not config.get('vid') or not config.get('pid'):
            return 0
        # --no-wait：Hook 在交互路径上，等不到回执会白等 2 秒，拖慢每条消息。
        # The host runs this hook in its own process with a hard timeout.
        args = ['send', state, '--yes', '--worker', '--no-wait', '--timeout', '0.5',
                '--vid', config['vid'], '--pid', config['pid']]
        if config.get('path'):
            args += ['--path', config['path']]
        with redirect_stdout(StringIO()):
            receiver_led.main(args)
    except (Exception, SystemExit) as exc:
        print('WB-SC hook: %s' % exc, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
