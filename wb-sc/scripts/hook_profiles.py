"""Host hook dialects used by the shared installer and receiver hook."""
from pathlib import Path
import sys

COMMON = {'SessionStart': 'idle', 'UserPromptSubmit': 'busy', 'Stop': 'done'}
PROFILES = {
    'workbuddy': ('.workbuddy/settings.json', dict(COMMON, StopFailure='error',
        PermissionRequest='wait', Notification='wait', PreCompact='compact', SessionEnd='idle')),
    'claude': ('.claude/settings.json', dict(COMMON, StopFailure='error',
        PermissionRequest='wait', Notification='wait', PreCompact='compact', SessionEnd='idle',
        PostToolUse='busy', PostCompact='busy')),
    'codex': ('.codex/hooks.json', dict(COMMON, PermissionRequest='wait',
        PreCompact='compact', PostCompact='busy', PostToolUse='busy', SessionEnd='idle', Interrupt='idle')),
    'cursor': ('.cursor/hooks.json', {'sessionStart': 'idle', 'sessionEnd': 'idle',
        'beforeSubmitPrompt': 'busy', 'stop': 'done', 'preCompact': 'compact'}),
    'copilot': ('.copilot/hooks/wb-sc.json', {'sessionStart': 'idle', 'sessionEnd': 'idle',
        'userPromptSubmitted': 'busy', 'agentStop': 'done', 'errorOccurred': 'error'}),
    'copilot-local': (None, dict(COMMON, PreCompact='compact', SessionEnd='idle')),
    'gemini': ('.gemini/settings.json', {'SessionStart': 'idle', 'SessionEnd': 'idle',
        'BeforeAgent': 'busy', 'AfterAgent': 'done', 'PreCompress': 'compact',
        'Notification': 'wait', 'AfterTool': 'busy'}),
    'trae': ('.trae-cn/hooks.json', dict(COMMON, Notification='wait', PostToolUse='busy')),
    'deepseek': (None, COMMON.copy()),
}


def paths(home, agent, hook_file=None):
    relative, _ = PROFILES[agent]
    if hook_file is None and relative is None:
        raise ValueError('This host requires --hook-file from its active configuration')
    settings = Path(hook_file).expanduser().resolve() if hook_file else home / relative
    return settings, settings.parent / 'wb-sc'


def registrations(agent, build_command):
    result = {}
    for event in PROFILES[agent][1]:
        arguments = () if agent == 'workbuddy' else ('--agent', agent, '--event', event)
        invocation = build_command(arguments)
        if agent == 'cursor':
            group = {'command': invocation, 'timeout': 6}
        elif agent == 'copilot':
            group = {'type': 'command', 'powershell' if sys.platform == 'win32' else 'bash': invocation,
                     'timeoutSec': 6}
        else:
            # Gemini timeouts are milliseconds; Codex SessionEnd is capped at 3 seconds.
            timeout = 6
            if agent == 'gemini':
                timeout = 6000
            elif agent == 'codex' and event == 'SessionEnd':
                timeout = 3
            group = {'hooks': [{'type': 'command', 'command': invocation, 'timeout': timeout}]}
        result[event] = [group]
    return result


def entries(settings):
    hooks = settings.get('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Existing hooks must be an object')
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError('Existing event hooks must be arrays')
        for group in groups:
            if not isinstance(group, dict):
                raise ValueError('Invalid existing hook group')
            children = group.get('hooks', [group])
            if not isinstance(children, list) or any(not isinstance(h, dict) for h in children):
                raise ValueError('Invalid existing hook handlers')
            for child in children:
                yield event, group, child


def command_of(handler):
    return handler.get('command') or handler.get('powershell') or handler.get('bash')


def state_for(agent, name, payload):
    state = PROFILES[agent][1].get(name)
    if state is None:
        return None
    if name == 'stop' and agent == 'cursor':
        return {'completed': 'done', 'aborted': 'idle', 'error': 'error'}.get(payload.get('status'))
    if name == 'Notification':
        kind = payload.get('notification_type', '')
        if kind in ('permission_prompt', 'ToolPermission', 'document_review',
                    'ask_user_question', 'browser_interaction', 'elicitation_dialog'):
            return 'wait'
        if kind == 'idle_prompt' and agent == 'trae':
            return 'done'
        if agent != 'workbuddy':
            return None
        text = str(payload).lower()
        return 'wait' if any(w in text for w in (
            'permission', 'approve', 'approval', 'allow', '授权', '权限', '确认', '允许')) else None
    return state
