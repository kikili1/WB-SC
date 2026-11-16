"""Shared host install lifecycle and documented status payload regressions."""
import base64
import contextlib
import io
import json
import subprocess
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hook_profiles as profiles
import remote_setup as setup
import status_hook as hook


class AgentHookTests(unittest.TestCase):
    def test_all_hosts_install_idempotently_and_remove_only_owned_hooks(self):
        for platform in ('win32', 'darwin'):
            for agent in profiles.PROFILES:
                with self.subTest(platform=platform, agent=agent), tempfile.TemporaryDirectory() as folder, \
                     patch.object(sys, 'platform', platform), patch.object(setup, 'usable_python', return_value=True), \
                     contextlib.redirect_stdout(io.StringIO()):
                    home = Path(folder)
                    custom = home / 'custom/hooks.json' if agent in ('deepseek', 'copilot-local') else None
                    settings, root = setup.paths(home, agent, custom)
                    original = {'other': {'keep': True}, 'hooks': {'Stop': [
                        {'hooks': [{'type': 'command', 'command': 'user-script'}]}]}}
                    if agent in ('cursor', 'copilot', 'copilot-local', 'trae'):
                        original['version'] = 1
                    settings.parent.mkdir(parents=True)
                    settings.write_bytes(setup.encode(original))
                    setup.operate('install', True, home, agent=agent, hook_file=custom)
                    self.assertTrue(setup.inspect(home, agent=agent, hook_file=custom)['ready'])
                    before = settings.read_bytes()
                    with patch.object(setup, 'atomic', side_effect=AssertionError('repeated write')):
                        setup.operate('install', True, home, agent=agent, hook_file=custom)
                    self.assertEqual(settings.read_bytes(), before)
                    setup.operate('uninstall', True, home, agent=agent, hook_file=custom)
                    self.assertEqual(setup.load(settings, {}), original)
                    self.assertFalse((root / 'runtime/status_hook.py').exists())

    def test_documented_events_map_to_states(self):
        fixtures = [
            ('codex', 'PermissionRequest', {}, 'wait'),
            ('codex', 'PostCompact', {}, 'busy'),
            ('codex', 'Interrupt', {}, 'idle'),
            ('claude', 'Notification', {'notification_type': 'permission_prompt'}, 'wait'),
            ('claude', 'Notification', {'message': 'permission mentioned in response'}, None),
            ('cursor', 'stop', {'status': 'completed'}, 'done'),
            ('cursor', 'stop', {'status': 'error'}, 'error'),
            ('cursor', 'stop', {'status': 'aborted'}, 'idle'),
            ('cursor', 'stop', {'status': 'future-value'}, None),
            ('copilot', 'userPromptSubmitted', {}, 'busy'),
            ('copilot', 'agentStop', {}, 'done'),
            ('copilot', 'subagentStop', {}, None),
            ('copilot-local', 'Stop', {}, 'done'),
            ('gemini', 'BeforeAgent', {}, 'busy'),
            ('gemini', 'AfterAgent', {}, 'done'),
            ('gemini', 'Notification', {'notification_type': 'ToolPermission'}, 'wait'),
            ('gemini', 'PreCompress', {}, 'compact'),
            ('trae', 'Notification', {'notification_type': 'document_review'}, 'wait'),
            ('trae', 'Notification', {'notification_type': 'idle_prompt'}, 'done'),
            ('deepseek', 'UserPromptSubmit', {}, 'busy'),
            ('deepseek', 'Stop', {}, 'done'),
            ('deepseek', 'PermissionRequest', {}, None),
            ('codex', 'Notification', {'notification_type': 'permission_prompt'}, None),
        ]
        for agent, event, payload, state in fixtures:
            with self.subTest(agent=agent, event=event, payload=payload):
                self.assertEqual(profiles.state_for(agent, event, payload), state)

    def test_dialects_timeouts_and_encoded_arguments(self):
        with patch.object(sys, 'platform', 'win32'):
            command = setup.hook_command(Path('C:/task $dir/wb-sc'), 'C:/Program Files/Python/python.exe',
                                         ('--agent', 'cursor', '--event', 'stop'))
            invocation = base64.b64decode(command.split()[-1]).decode('utf-16-le')
            self.assertIn("'--agent' 'cursor' '--event' 'stop'", invocation)
            copilot = profiles.registrations('copilot', lambda args: 'python hook.py ' + ' '.join(args))
            self.assertIn('powershell', copilot['agentStop'][0])
        self.assertEqual(profiles.registrations('gemini', lambda args: 'cmd ' + ' '.join(args))['AfterAgent'][0]['hooks'][0]['timeout'], 6000)
        self.assertEqual(profiles.registrations('codex', lambda args: 'cmd ' + ' '.join(args))['SessionEnd'][0]['hooks'][0]['timeout'], 3)
        with self.assertRaises(ValueError):
            setup.paths(Path('.'), 'deepseek')

    def test_hook_output_and_failure_never_block_or_expose_prompt(self):
        for agent, event in (('gemini', 'BeforeAgent'), ('copilot', 'agentStop'), ('codex', 'Stop')):
            payload = json.dumps({'prompt': 'private text'}).encode()
            with self.subTest(agent=agent), patch.object(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(payload))), \
                 patch.object(hook.receiver_led, 'read_config', return_value={'vid': '1915', 'pid': '1025'}), \
                 patch.object(hook.receiver_led, 'main', side_effect=OSError('device absent')) as send, \
                 contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(hook.main(['--agent', agent, '--event', event]), 0)
                self.assertEqual(json.loads(out.getvalue()), {})
                self.assertNotIn('private text', str(send.call_args))
        for payload in (b'[]', b'broken', b'{"hook_event_name":"wrong"}'):
            with patch.object(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(payload))), \
                 patch.object(hook.receiver_led, 'main') as send, \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(hook.main(['--agent', 'codex', '--event', 'Stop']), 0)
                send.assert_not_called()

    def test_flat_configs_rollback_and_cross_host_isolation(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sys, 'platform', 'win32'), \
             patch.object(setup, 'usable_python', return_value=True), contextlib.redirect_stdout(io.StringIO()):
            home = Path(folder)
            settings, root = setup.paths(home, 'cursor')
            settings.parent.mkdir()
            original = b'{"version":1,"hooks":{"stop":[{"command":"user-script"}]}}'
            settings.write_bytes(original)
            atomic = setup.atomic
            def fail(path, data):
                if path == settings:
                    raise OSError('injected failure')
                atomic(path, data)
            with patch.object(setup, 'atomic', side_effect=fail), self.assertRaises(OSError):
                setup.operate('install', True, home, agent='cursor')
            self.assertEqual(settings.read_bytes(), original)
            self.assertFalse((root / 'runtime/status_hook.py').exists())
            setup.operate('install', True, home, agent='cursor')
            setup.operate('install', True, home, agent='codex')
            setup.operate('uninstall', True, home, agent='cursor')
            self.assertTrue(setup.inspect(home, agent='codex')['ready'])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows registered command integration')
    def test_installed_encoded_command_keeps_host_and_event_arguments(self):
        with tempfile.TemporaryDirectory(prefix='wb-sc $ ') as folder, \
             contextlib.redirect_stdout(io.StringIO()):
            home = Path(folder)
            setup.operate('install', True, home, agent='cursor')
            settings, _ = setup.paths(home, 'cursor')
            command = setup.load(settings, {})['hooks']['stop'][0]['command']
            # An unknown status must emit JSON and do no HID work; exercises the real copied runtime.
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                    input='{"status":"fixture-with-no-hid"}',
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})
            self.assertEqual(result.stderr, '')
