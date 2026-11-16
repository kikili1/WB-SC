"""Hardware-free platform, HID and installation regression tests."""
import contextlib
import io
import json
import os
from pathlib import Path
import queue
import shlex
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mac_hid
import receiver_led
import remote_setup
import wbsc

# Report 8 input = 16 data bytes; report 5 output = 63 data bytes.
DESCRIPTOR = bytes.fromhex('85 08 75 08 95 10 81 02 85 05 95 3F 91 02')


class PlatformTests(unittest.TestCase):
    def run_command(self, function, platform='darwin', **args):
        with patch.object(sys, 'platform', platform), contextlib.redirect_stdout(io.StringIO()) as out:
            result = function(SimpleNamespace(**args))
        return result, out.getvalue()

    def test_mac_list_and_plan(self):
        _, output = self.run_command(wbsc.cmd_list, target='desktop')
        self.assertIn('默认键(mac)', output)
        self.assertIn('Meta+D', output)
        self.assertNotIn('Ctrl+D', output)
        _, output = self.run_command(wbsc.cmd_plan, id='toggle-voice-recording', binding='Cmd+J')
        self.assertIn('"mac": "Meta+J"', output)
        self.assertNotIn('"win":', output)

    def test_platform_conflicts(self):
        for platform, binding, expected in [('darwin', 'Ctrl+D', 0), ('win32', 'Ctrl+D', 1),
                                             ('darwin', 'Cmd+D', 1), ('darwin', 'Cmd+Space', 1)]:
            result, output = self.run_command(wbsc.cmd_check, platform, binding=binding, target='desktop')
            self.assertEqual(result, expected, output)
        _, output = self.run_command(wbsc.cmd_check, binding='Option+Shift+P', target='desktop')
        self.assertNotIn('Windows', output)
        self.assertIn('静态检查', output)

    def test_native_selection_and_no_eager_dependency(self):
        with patch.object(sys, 'platform', 'darwin'):
            self.assertIs(receiver_led.native(), mac_hid)
        with patch.dict(sys.modules, {'hid': None}), self.assertRaisesRegex(OSError, 'pip install hidapi'):
            mac_hid.load_hid()

    def test_mac_node_paths(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(wbsc.Path, 'home', return_value=Path(folder)), \
                patch.object(sys, 'platform', 'darwin'), patch.object(wbsc.shutil, 'which', return_value=None):
            node = Path(folder) / '.workbuddy/binaries/node/versions/22/bin/node'
            node.parent.mkdir(parents=True)
            node.touch()
            self.assertEqual(wbsc.find_node(), str(node))

    def test_bridge_actions_never_inject(self):
        for name in ('send-message', 'toggle-window'):
            with patch.object(wbsc, 'cdp_alive', side_effect=AssertionError('CDP accessed')):
                result, output = self.run_command(wbsc.cmd_apply_desktop, id=name, binding='Meta+J', via='cdp')
            self.assertEqual(result, 2)
            self.assertIn('GUI', output)
            self.assertNotIn('--via cdp', output)

    def test_detect_distinguishes_directory_and_running_state(self):
        with patch.object(sys, 'platform', 'darwin'), patch.object(wbsc, 'leveldb_state', return_value='writable'), \
                patch.object(wbsc, 'cdp_alive', return_value=False):
            result = wbsc.detect()
        self.assertEqual(result['platform'], 'darwin')
        self.assertEqual(result['app_running'], 'unknown')
        self.assertEqual(result['leveldb_state'], 'writable')

    def test_cli_preserves_ctrl_and_backs_up(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'keybindings.json'
            config.write_text('{"bindings":[],"user":true}', encoding='utf-8')
            with patch.object(wbsc, 'CLI_CONFIG', config):
                result, _ = self.run_command(wbsc.cmd_apply_cli, context='Chat', binding='ctrl+j',
                                             action='chat:newline', unbind=False, yes=True)
            self.assertEqual(result, 0)
            self.assertTrue(json.loads(config.read_text())['user'])
            self.assertEqual(json.loads(config.read_text())['bindings'][0]['bindings'], {'ctrl+j': 'chat:newline'})
            self.assertEqual(len(list(Path(folder).glob('*.bak-*'))), 1)


class HidTests(unittest.TestCase):
    def info(self):
        return mac_hid.HidDeviceInfo('70617468', 0x1915, 0x1025, 1, 0xFF01, 1, 17, 64, 0, '', {'5': 64})

    def test_descriptor_lengths_push_pop_bits_and_long_items(self):
        result = mac_hid.report_lengths(DESCRIPTOR)
        self.assertEqual(result[8], {'8': 17})
        self.assertEqual(result[9], {'5': 64})
        descriptor = bytes.fromhex('85 05 75 01 95 03 91 02 A4 75 08 95 01 91 02 B4 91 02 FE 01 00 FF')
        self.assertEqual(mac_hid.report_lengths(descriptor)[9], {'5': 3})
        self.assertEqual(mac_hid.report_lengths(bytes.fromhex('75 08 95 10 81 02'))[8], {'0': 16})

    def test_invalid_descriptors_rejected(self):
        for descriptor in (b'', b'\x75', b'\xFE', b'\xFE\x05\x00\x01', b'\xB4',
                           bytes.fromhex('85 00'), bytes.fromhex('81 02'), DESCRIPTOR + b'\xA4'):
            with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                mac_hid.report_lengths(descriptor)

    def test_enumeration_lengths_paths_filter_and_close(self):
        hid = MagicMock()
        item = dict(path=b'path', vendor_id=0x1915, product_id=0x1025, release_number=1,
                    usage_page=0xFF01, usage=1)
        hid.enumerate.return_value = [dict(item, usage_page=1), item, item]
        hid.device.return_value.get_report_descriptor.return_value = list(DESCRIPTOR)
        devices = mac_hid.enumerate_native(hid)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['path'], b'path'.hex())
        self.assertEqual(devices[0]['output_report_length'], 64)
        hid.device.return_value.close.assert_called_once()
        hid.device.return_value.get_report_descriptor.side_effect = OSError('access denied')
        with self.assertRaisesRegex(OSError, 'access denied'):
            mac_hid.enumerate_native(hid)
        self.assertEqual(hid.device.return_value.close.call_count, 2)

    def test_read_write_share_worker_and_close(self):
        worker = MagicMock()
        worker.request.side_effect = [None, None, [8, 1], [], OSError('disconnected')]
        with patch.object(mac_hid, 'Worker', return_value=worker):
            with mac_hid.open_reader(self.info()) as read:
                mac_hid.write_report(self.info(), b'\x05\x43', 1)
                self.assertEqual(read(0.1), b'\x08\x01')
                self.assertIsNone(read(0.1))
                self.assertIsNone(read(0))
                with self.assertRaisesRegex(OSError, 'disconnected'):
                    read(0.1)
        write = worker.request.call_args_list[1]
        self.assertEqual(bytes.fromhex(write.kwargs['data']), b'\x05\x43' + bytes(62))
        worker.close.assert_called_once()
        self.assertFalse(mac_hid._readers)

    def test_write_validation_and_timeout_cleanup(self):
        for payload in (b'', b'\x04\x00', b'\x05' + bytes(64)):
            with patch.object(mac_hid, 'Worker', side_effect=AssertionError('opened')), self.assertRaises(ValueError):
                mac_hid.write_report(self.info(), payload, 1)
        worker = MagicMock()
        worker.request.side_effect = [None, TimeoutError('write timed out')]
        with patch.object(mac_hid, 'Worker', return_value=worker), self.assertRaises(TimeoutError):
            mac_hid.write_report(self.info(), b'\x05', 1)
        worker.close.assert_called_once()

    def test_worker_timeout_and_exit(self):
        worker = object.__new__(mac_hid.Worker)
        worker.process = MagicMock()
        worker.close = MagicMock()
        worker.replies = queue.Queue()
        with self.assertRaises(TimeoutError):
            worker.request('write', timeout=0.001)
        worker.close.assert_called_once()
        worker.replies.put(None)
        with self.assertRaisesRegex(OSError, 'exited'):
            worker.request('read')

    def test_worker_serve_short_write_and_disconnect_close(self):
        hid = MagicMock()
        hid.device.return_value.get_report_descriptor.return_value = DESCRIPTOR
        hid.device.return_value.write.return_value = 1
        hid.device.return_value.read.side_effect = OSError('disconnected')
        commands = [dict(operation='open', path='70617468'), dict(operation='write', data=(b'\x05\x43' + bytes(62)).hex()),
                    dict(operation='read', length=17, milliseconds=1)]
        with patch.object(mac_hid, 'load_hid', return_value=hid), \
                patch.object(sys, 'stdin', io.StringIO(''.join(json.dumps(c) + '\n' for c in commands))), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            mac_hid.serve()
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertIn('Short HID write', responses[1]['error'])
        self.assertEqual(responses[2]['error'], 'disconnected')
        hid.device.return_value.close.assert_called_once()

    def test_real_worker_round_trip_and_timeout_without_hardware(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = Path(folder) / 'hid.py'
            fixture.write_text('''import time
class device:
    def open_path(self, path): pass
    def close(self): pass
    def get_report_descriptor(self):
        return bytes.fromhex('85 08 75 08 95 10 81 02 85 05 95 3F 91 02')
    def write(self, data):
        if data[1] == 255: time.sleep(10)
        return len(data)
    def read(self, length, milliseconds): return [8, 1]
''', encoding='utf-8')
            with patch.dict(os.environ, {'PYTHONPATH': folder}):
                with mac_hid.open_reader(self.info()) as read:
                    worker = mac_hid._readers[self.info().path]
                    mac_hid.write_report(self.info(), b'\x05\x43', 1)
                    self.assertEqual(read(0.1), b'\x08\x01')
                    started = time.monotonic()
                    with self.assertRaises(TimeoutError):
                        mac_hid.write_report(self.info(), b'\x05\xFF', 0.05)
                    self.assertLess(time.monotonic() - started, 3)
                    self.assertIsNotNone(worker.process.poll())
                self.assertFalse(mac_hid._readers)


class MacInstallTests(unittest.TestCase):
    def setUp(self):
        self._usable_python = remote_setup.usable_python
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        for patcher in (patch.object(sys, 'platform', 'darwin'),
                        patch.object(remote_setup, 'usable_python', return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.settings, self.root = remote_setup.paths(self.home)
        self.settings.parent.mkdir()
        self.original = {'user': True, 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'user-hook'}]}]}}
        self.settings.write_bytes(remote_setup.encode(self.original))

    def test_install_upgrade_uninstall_preserves_user_and_modified_files(self):
        remote_setup.operate('install', True, self.home)
        manifest = remote_setup.load(self.root / 'installed.json', {})
        self.assertEqual(manifest['platform'], 'darwin')
        self.assertEqual(set(manifest['hashes']), set(remote_setup.MAC_FILES))
        command = manifest['commands'][0]
        self.assertNotIn('powershell', command)
        self.assertEqual(shlex.split(command)[1], '-B')
        self.assertTrue(remote_setup.inspect(self.home)['ready'])
        config = self.root / 'config.json'
        original_config = config.read_bytes()
        manifest['version'] = 'old'
        (self.root / 'installed.json').write_bytes(remote_setup.encode(manifest))
        remote_setup.operate('install', True, self.home)
        self.assertEqual(config.read_bytes(), original_config)
        runtime = self.root / 'runtime/mac_hid.py'
        runtime.write_text('# user edit', encoding='utf-8')
        remote_setup.operate('uninstall', True, self.home)
        self.assertEqual(remote_setup.load(self.settings, {}), self.original)
        self.assertTrue(runtime.exists())
        self.assertTrue(config.exists())

    def test_quotes_round_trip(self):
        root = self.home / "a space ' and 中文"
        python = str(self.home / "Python 'quoted path'/bin/python3")
        command = remote_setup.hook_command(root, python)
        self.assertEqual(shlex.split(command), [python, '-B', str(root / 'runtime/status_hook.py')])

    def test_upgrade_replaces_old_command_and_removes_only_owned_stale_files(self):
        import hashlib
        remote_setup.operate('install', True, self.home)
        manifest_path = self.root / 'installed.json'
        manifest = remote_setup.load(manifest_path, {})
        old_command = 'powershell.exe old-wb-sc-command'
        data = remote_setup.load(self.settings, {})
        for groups in data['hooks'].values():
            for group in groups:
                for hook in group['hooks']:
                    if hook['command'] in manifest['commands']:
                        hook['command'] = old_command
        self.settings.write_bytes(remote_setup.encode(data))
        for name in ('run.ps1', 'win_hid.py'):
            content = b'old runtime'
            (self.root / 'runtime' / name).write_bytes(content)
            manifest['hashes'][name] = hashlib.sha256(content).hexdigest()
        (self.root / 'runtime/win_hid.py').write_bytes(b'user modification')
        manifest.update(platform='win32', commands=[old_command])
        manifest_path.write_bytes(remote_setup.encode(manifest))
        remote_setup.operate('install', True, self.home)
        self.assertNotIn(old_command, self.settings.read_text(encoding='utf-8'))
        self.assertFalse((self.root / 'runtime/run.ps1').exists())
        self.assertEqual((self.root / 'runtime/win_hid.py').read_bytes(), b'user modification')
        self.assertTrue(remote_setup.inspect(self.home)['ready'])

    def test_doctor_reports_access_failure_without_probing(self):
        api = SimpleNamespace(enumerate_hid_devices=MagicMock(side_effect=OSError('access denied')))
        with patch.object(receiver_led, 'native', return_value=api), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(remote_setup.doctor(self.home), 1)
        self.assertIn('access denied', out.getvalue())

    def test_interpreter_check_imports_hid_in_selected_python(self):
        # Exercise the real check rather than the installation fixture's mock.
        function = self._usable_python
        with patch.object(remote_setup.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(function(sys.executable))
        self.assertIn('import hid', run.call_args.args[0][-1])
        self.assertIn('(3, 10)', run.call_args.args[0][-1])

    def test_rollback_and_missing_dependency_before_mutation(self):
        original = self.settings.read_bytes()
        with patch.object(remote_setup, 'usable_python', return_value=False), self.assertRaises(OSError):
            remote_setup.operate('install', True, self.home)
        self.assertEqual(self.settings.read_bytes(), original)
        self.assertFalse(self.root.exists())
        atomic = remote_setup.atomic
        def fail(path, data):
            if path.name == 'installed.json':
                raise OSError('injected')
            atomic(path, data)
        with patch.object(remote_setup, 'atomic', side_effect=fail), self.assertRaises(OSError):
            remote_setup.operate('install', True, self.home)
        self.assertEqual(self.settings.read_bytes(), original)
        self.assertFalse((self.root / 'runtime/mac_hid.py').exists())


if __name__ == '__main__':
    unittest.main()
