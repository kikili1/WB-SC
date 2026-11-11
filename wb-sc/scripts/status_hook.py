"""Installed command Hook. Never blocks the user's prompt on device failure."""
from contextlib import redirect_stdout
from io import StringIO
import json
import sys
import receiver_led

EVENTS = {'UserPromptSubmit': 'busy', 'Stop': 'done', 'StopFailure': 'error',
          'SessionStart': 'idle', 'SessionEnd': 'idle',
          # 等待人工确认：唯一需要用户动手的状态，用黄色呼吸循环提示。
          'PermissionRequest': 'wait',
          # 只关心权限类通知；其它 Notification 不点灯（下面会再过滤一次）。
          'Notification': 'wait',
          # 长会话整理上下文，紫色呼吸，避免被误判为卡死。
          'PreCompact': 'compact'}

# 不同版本/语言的 Notification 载荷用词不同，命中任一即视为需要人工确认。
ATTENTION_WORDS = ('permission', 'approve', 'approval', 'allow', '授权', '权限', '确认', '允许')


def main():
    try:
        data = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError('Hook input exceeds 1 MiB')
        event = json.loads(data.decode('utf-8-sig'))
        state = EVENTS.get(event.get('hook_event_name'))
        if state is None:
            return 0
        if event.get('hook_event_name') == 'Notification':
            text = json.dumps(event, ensure_ascii=False).lower()
            if not any(word in text for word in ATTENTION_WORDS):
                return 0
        # shortcut: latest session wins; aggregate if concurrent chats must share one LED.
        # 配置解析与手动命令共用一处：安装后读 ~/.workbuddy/wb-sc/config.json。
        config = receiver_led.read_config()
        if not config.get('vid') or not config.get('pid'):
            return 0
        # --no-wait：Hook 在交互路径上，等不到回执会白等 2 秒，拖慢每条消息。
        # WorkBuddy already runs this hook in its own process with a hard timeout.
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
    sys.exit(main())
