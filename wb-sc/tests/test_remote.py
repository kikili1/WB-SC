import contextlib
import ctypes
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import receiver_led as led
import remote_setup as setup
import status_hook as hook
import vendor_info
import wbsc
import key_push


class ResetTests(unittest.TestCase):
    def args(self, yes=True):
        return SimpleNamespace(yes=yes, json=True, timeout=0.2, vid=0x1915, pid=0x1025, path=None)

    def test_preview_never_opens_device(self):
        with patch.object(led, 'native') as native, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(key_push.reset(self.args(False)), 0)
        native.assert_not_called()
        result = json.loads(out.getvalue())
        self.assertEqual(result['outcome'], 'preview')
        packet = bytes.fromhex(result['tx'])
        self.assertEqual(packet, bytes((5, 0x44, 2, 1, result['token'])))

    def test_only_matching_execution_result_is_accepted(self):
        for status in range(4):
            with self.subTest(status=status):
                api = MagicMock()
                read = api.open_reader.return_value.__enter__.return_value
                read.side_effect = [bytes((8, 0xAA)) + bytes(15),
                                    bytes((8, 0x44, 8, 0)) + bytes(13),
                                    bytes((8, 0x44, 7, status)) + bytes(13)]
                with patch.object(led, 'native', return_value=api), \
                        patch.object(key_push, 'find_device', return_value=object()), \
                        patch.object(key_push.secrets, 'randbelow', return_value=7), \
                        contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(key_push.reset(self.args()), int(status != 0))
                self.assertEqual(json.loads(out.getvalue())['status'], status)
                api.write_report.assert_called_once()

    def test_timeout_is_unknown_without_retry(self):
        api = MagicMock()
        api.open_reader.return_value.__enter__.return_value.return_value = None
        with patch.object(led, 'native', return_value=api), \
                patch.object(key_push, 'find_device', return_value=object()), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(key_push.reset(self.args()), 1)
        self.assertEqual(json.loads(out.getvalue())['outcome'], 'unknown')
        api.write_report.assert_called_once()


class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name)
        self.settings, self.root = setup.paths(self.home)
        self.settings.parent.mkdir()
        self.original = {'sandbox': {'enabled': True}, 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'user-hook'}]}]}}
        self.settings.write_bytes(setup.encode(self.original))

    def test_install_upgrade_uninstall_preserves_user(self):
        old = setup.hook_command(self.root)
        legacy = setup.load(self.settings, {})
        legacy['hooks']['Stop'].append({'hooks': [{'type': 'command', 'command': old}]})
        self.settings.write_bytes(setup.encode(legacy))
        setup.operate('install', True, self.home)
        config = self.root / 'config.json'
        config.write_bytes(setup.encode({'vid': '1915', 'pid': '1025', 'path': 'chosen'}))
        with patch.object(setup, 'atomic', side_effect=AssertionError('current install rewrote files')):
            setup.operate('install', True, self.home)
        self.assertTrue(setup.operate('status', home=self.home)['ready'])
        data = setup.load(self.settings, {})
        self.assertEqual(len(data['hooks']['Stop']), 2)
        self.assertNotIn(old, [h['command'] for group in data['hooks']['Stop'] for h in group['hooks']])
        self.assertEqual(setup.load(config, {})['path'], 'chosen')
        changed = self.root / 'runtime/run.ps1'
        changed.write_text('# user edit', encoding='utf-8')
        setup.operate('uninstall', True, self.home)
        self.assertEqual(setup.load(self.settings, {}), self.original)
        self.assertTrue(changed.exists())
        self.assertTrue(config.exists())

    def test_malformed_and_rollback(self):
        self.settings.write_text('broken json', encoding='utf-8')
        with self.assertRaises(ValueError): setup.operate('install', True, self.home)
        self.assertFalse(self.root.exists())
        self.settings.write_bytes(setup.encode(self.original))
        original_bytes = self.settings.read_bytes()
        original_atomic = setup.atomic
        def fail(path, data):
            if path.name == 'installed.json': raise OSError('injected failure')
            original_atomic(path, data)
        with patch.object(setup, 'atomic', side_effect=fail), self.assertRaises(OSError):
            setup.operate('install', True, self.home)
        self.assertEqual(self.settings.read_bytes(), original_bytes)
        self.assertFalse((self.root / 'runtime/receiver_led.py').exists())

    def test_concurrent_settings_change_survives_rollback(self):
        later = dict(self.original, new_user_value=True)
        original_atomic = setup.atomic
        def concurrent(path, data):
            original_atomic(path, data)
            if path.name == 'installed.json':
                self.settings.write_bytes(setup.encode(later))
        with patch.object(setup, 'atomic', side_effect=concurrent), self.assertRaises(OSError):
            setup.operate('install', True, self.home)
        self.assertEqual(setup.load(self.settings, {}), later)
        self.assertFalse((self.root / 'runtime/receiver_led.py').exists())

    def test_isolated_runtime_no_host_dependency(self):
        setup.operate('install', True, self.home)
        installed = self.root / 'runtime/receiver_led.py'
        result = subprocess.run([sys.executable, str(installed), 'send', 'busy'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('05 43 01 01', result.stdout)
        for name in setup.FILES:
            text = (self.root / 'runtime' / name).read_text(encoding='utf-8')
            self.assertNotIn('dongle_host', text)
            self.assertNotIn('hid_push', text)

    def test_hook_no_stdout_and_does_not_pass_prompt(self):
        setup.operate('install', True, self.home)
        payload = json.dumps({'hook_event_name': 'UserPromptSubmit', 'prompt': 'private prompt'}).encode()
        def fake_send(args):
            print('sender diagnostic')
            self.assertEqual(args[:3], ['send', 'busy', '--yes'])
            self.assertIn('--worker', args)
            self.assertIn('--no-wait', args)
            self.assertNotIn('private prompt', args)
            return 1
        with patch.object(hook, '__file__', str(self.root / 'runtime/status_hook.py')), \
             patch.object(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(payload))), \
             patch.object(led, 'main', side_effect=fake_send), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(hook.main(), 0)
        self.assertEqual(out.getvalue(), '')

    def test_registered_command_reads_utf8_without_sending(self):
        setup.operate('install', True, self.home)
        command = setup.load(self.settings, {})['hooks']['SessionStart'][0]['hooks'][0]['command']
        payload = json.dumps({'hook_event_name': 'Unknown', 'prompt': '测试中文"反斜杠\\和 emoji 🎯'},
                             ensure_ascii=False).encode('utf-8')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-Command', command],
                                input=payload, capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'', b''))

    def test_sender_selection_frames_and_timeout(self):
        for state, value in led.STATES.items(): self.assertEqual(led.packet(state), bytes([5,67,1,value]))
        info = SimpleNamespace(vendor_id=0x1915, product_id=0x1025, usage_page=0xff02,
                               input_report_length=17, output_report_length=64, path='chosen')
        for devices in ([], [info, info]):
            with patch.object(led, 'native', return_value=SimpleNamespace(enumerate_hid_devices=lambda: devices)), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(led.main(['send','busy','--yes']), 1)
        with patch.object(led, 'native', return_value=SimpleNamespace(enumerate_hid_devices=lambda: [info])), \
             patch.object(led.subprocess, 'run', side_effect=subprocess.TimeoutExpired('worker',3)), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(led.main(['send','busy','--yes','--path','chosen']), 1)
        other = SimpleNamespace(**dict(vars(info), path='other'))
        api = SimpleNamespace(enumerate_hid_devices=lambda: [other, info], write_report=MagicMock())
        with patch.object(led, 'native', return_value=api), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(led.main(['send','done','--yes','--worker','--no-wait','--path','chosen']), 0)
        api.write_report.assert_called_once_with(info, bytes.fromhex('05 43 01 02'), 2)
        with patch.object(led, 'native', side_effect=AssertionError('parent enumerated devices')), \
             patch.object(led.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'sent', '')) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(led.main(['send','done','--yes','--no-wait']), 0)
        self.assertIn('--worker', run.call_args.args[0])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            led.main(['send','done','--vid','10000'])
        self.assertEqual(error.exception.code, 2)

    def test_windows_write_cleanup(self):
        import win_hid as hid
        info = SimpleNamespace(output_report_length=64, path='chosen')
        api = MagicMock()
        api.CreateEventW.return_value = 22
        def write(handle, buf, length, count, overlap):
            self.assertEqual(bytes(buf), bytes.fromhex('05 43 01 01') + bytes(60))
            ctypes.cast(count, ctypes.POINTER(ctypes.wintypes.DWORD)).contents.value = length
            return True
        api.WriteFile.side_effect = write
        with patch.object(hid, 'kernel32', api), patch.object(hid, '_open_handle', return_value=11) as open_handle:
            hid.write_report(info, led.packet('busy'),2)
            open_handle.assert_called_with('chosen',read=False,write=True,flags=0x40000000)
        self.assertEqual(api.CloseHandle.call_count,2)
        api.reset_mock()
        def pending(*args): ctypes.set_last_error(997); return False
        api.WriteFile.side_effect = pending
        api.WaitForSingleObject.return_value = 258
        with patch.object(hid,'kernel32',api),patch.object(hid,'_open_handle',return_value=11),self.assertRaises(TimeoutError):
            hid.write_report(info,led.packet('busy'),2)
        api.CancelIoEx.assert_called_once()
        self.assertEqual(api.CloseHandle.call_count,2)
        api.reset_mock()
        def short(*args): ctypes.cast(args[3],ctypes.POINTER(ctypes.wintypes.DWORD)).contents.value=3; return True
        api.WriteFile.side_effect=short
        with patch.object(hid,'kernel32',api),patch.object(hid,'_open_handle',return_value=11),self.assertRaises(OSError):
            hid.write_report(info,led.packet('busy'),2)
        self.assertEqual(api.CloseHandle.call_count,2)


class KeyPushTests(unittest.TestCase):
    def test_key_push_validates_reply_and_reports_unknown_without_retry(self):
        config = {'variant': 'HM-AItest-1', 'variant_confirmed': True}
        device = SimpleNamespace(path='chosen', vendor_id=0x1915, product_id=0x1025, usage_page=0xff01,
                                 input_report_length=17, output_report_length=64)
        for reply, expected in ((0, 'saved'), (3, 'busy'), (None, 'unknown')):
            with self.subTest(outcome=expected):
                sent = []

                @contextlib.contextmanager
                def open_reader(info):
                    self.assertIs(info, device)
                    self.assertFalse(sent)
                    reports = iter((bytes.fromhex('08 18 04 39 2A 00 00'),
                                    bytes.fromhex('08 39 2B 00') + bytes(13),
                                    bytes.fromhex('08 39 2A 00 FF') + bytes(12),
                                    bytes.fromhex('08 39 2A 00'),
                                    bytes((8, 0x39, 42, reply)) + bytes(13) if reply is not None else None))
                    yield lambda timeout: next(reports)

                api = SimpleNamespace(enumerate_hid_devices=lambda: [device], open_reader=open_reader,
                                      write_report=lambda info, payload, timeout: sent.append(payload))
                argv = ['wbsc.py', 'key', 'push', '--name', 'K_S1', '--key', 'Alt+Shift+T', '--yes', '--json']
                with patch.object(sys, 'argv', argv), patch.object(led, 'read_config', return_value=config), \
                     patch.object(led, 'native', return_value=api), patch('key_push.secrets.randbelow', return_value=42), \
                     contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as exit_code:
                    wbsc.main()
                self.assertEqual(exit_code.exception.code, int(reply != 0))
                self.assertEqual(sent, [bytes.fromhex('05 39 05 2A 00 00 66 17')])
                self.assertEqual(json.loads(output.getvalue())['outcome'], expected)

    def test_old_config_allows_preview_but_requires_confirmation_for_named_write(self):
        argv = ['wbsc.py', 'key', 'push', '--name', 'K_S1', '--key', 'F4', '--json']
        for flags, expected in (([], 'preview'), (['--yes'], 'error')):
            with patch.object(sys, 'argv', argv + flags), \
                 patch.object(led, 'read_config', return_value={'variant': 'HM-AItest-1'}), \
                 patch.object(led, 'native', side_effect=AssertionError('unexpected hardware access')), \
                 contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as exit_code:
                wbsc.main()
            self.assertEqual(exit_code.exception.code, int(bool(flags)))
            self.assertEqual(json.loads(output.getvalue())['outcome'], expected)


class VendorInfoTests(unittest.TestCase):
    def test_query_frame_and_decoding(self):
        self.assertEqual(vendor_info.QUERY, bytes.fromhex('04 1F 00 00 00 00 00 00 72'))
        self.assertEqual(vendor_info.decode(bytes.fromhex('08 18 04 0D 0C 0B 0A')), ('cs', '0A0B0C0D'))
        self.assertEqual(vendor_info.decode(bytes.fromhex('08 1F 00 00')), ('query-ack', ''))
        self.assertEqual(vendor_info.decode(b'\x08\x13' + bytes([6, 0]) + b'W306A1'),
                         ('version', 'W306A1'))
        self.assertEqual(vendor_info.decode(b'\x08\x12' + bytes([4, 0]) + b'-45'), ('rssi', '-45'))
        self.assertIsNone(vendor_info.decode(bytes.fromhex('08 99 01 00')))
        self.assertIsNone(vendor_info.decode(b'\xAA\xAA\xAA'))

    def test_collect_sends_query_and_merges_version(self):
        reports = [bytes.fromhex('08 18 02 34 12'),
                   b'\x08\x13' + bytes([3, 0]) + b'W30',
                   b'\x08\x13' + bytes([3, 0]) + b'6A1',
                   bytes.fromhex('08 1F 00 00')]
        api = SimpleNamespace(write_report=MagicMock(), open_reader=lambda dev: contextlib.nullcontext(
            lambda timeout: reports.pop(0) if reports else None))
        found = vendor_info.collect(api, 'dev', 0.5)
        api.write_report.assert_called_once_with('dev', vendor_info.QUERY, 0.5)
        self.assertEqual(found['cs'], '1234')
        self.assertEqual(found['version'], 'W306A1')
        self.assertEqual(found['query-ack'], '')


if __name__ == '__main__':
    unittest.main()
