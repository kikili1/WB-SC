"""Selected-host device configuration must reach every manual device operation."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import key_push
import keymap_rc
import receiver_led as led
import remote_setup as setup
import status_hook
import vendor_info
import wbsc


class DeviceConfigTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        self.configs = []
        for agent, vid, pid, variant in (('workbuddy', '1915', '1025', 'HM-AItest-1'),
                                          ('codex', '1234', '5678', 'second-layout')):
            _, root = setup.paths(self.home, agent)
            root.mkdir(parents=True)
            path = root / 'config.json'
            path.write_bytes(setup.encode(dict(vid=vid, pid=pid, path=agent + '-device',
                                               variant=variant, variant_confirmed=True)))
            self.configs.append(path)

    def cli(self, *argv):
        with patch.object(sys, 'argv', ['wbsc.py', *map(str, argv)]), \
             contextlib.redirect_stdout(io.StringIO()) as out, \
             contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as result:
            wbsc.main()
        self.assertIsNone(led.CONFIG_PATH)
        return result.exception.code, out.getvalue(), err.getvalue()

    def test_selected_host_reaches_led_key_query_and_reset(self):
        cases = [(('led', 'send', 'busy'), led, 'execute'),
                 (('key', 'push', '--col', '0', '--row', '0', '--key', 'Enter'), key_push, 'execute'),
                 (('remote', 'info'), vendor_info, 'execute'),
                 (('remote', 'reset', '--json'), key_push, 'reset')]
        for path in self.configs:
            config = setup.load(path, {})
            for argv, module, function in cases:
                with self.subTest(host=path.parent.parent.name, command=argv), \
                     patch.object(module, function, return_value=0) as execute:
                    code, _, err = self.cli('--config', path, *argv)
                    self.assertEqual(code, 0, err)
                    args = execute.call_args.args[0]
                    self.assertEqual((args.vid, args.pid, args.path),
                                     (int(config['vid'], 16), int(config['pid'], 16), config['path']))

    def test_variant_read_and_confirmation_write_use_selected_config(self):
        second = dict(note='fixture', keys={'K_S1': dict(pos=(0, 1), factory=0x28, note='fixture')})
        old_bytes = self.configs[0].read_bytes()
        with patch.dict(keymap_rc.VARIANTS, {'second-layout': second}):
            code, out, err = self.cli('--config', self.configs[1], 'key', 'list')
            self.assertEqual(code, 0, err)
            self.assertIn('second-layout', out)
            self.assertIn('C0/R1', out)
            code, _, err = self.cli('--config', self.configs[1], 'key', 'use', '--variant', 'HM-AItest-1')
            self.assertEqual(code, 0, err)
        self.assertEqual(setup.load(self.configs[1], {})['variant'], 'HM-AItest-1')
        self.assertEqual(self.configs[0].read_bytes(), old_bytes)

    def test_manual_and_hook_device_selection_agree(self):
        path = self.configs[1]
        with patch.object(led, 'execute', return_value=0) as execute:
            self.assertEqual(self.cli('--config', path, 'led', 'send', 'busy')[0], 0)
            manual = execute.call_args.args[0]
        with patch.object(led, '__file__', str(path.parent / 'runtime/receiver_led.py')), \
             patch.object(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'{}'))), \
             patch.object(led, 'main', return_value=0) as send, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(status_hook.main(['--agent', 'codex', '--event', 'UserPromptSubmit']), 0)
        argv = send.call_args.args[0]
        self.assertEqual(argv[argv.index('--vid') + 1], '%04x' % manual.vid)
        self.assertEqual(argv[argv.index('--pid') + 1], '%04x' % manual.pid)
        self.assertEqual(argv[argv.index('--path') + 1], manual.path)

    def test_explicit_invalid_config_fails_without_fallback_or_device_access(self):
        invalid = self.home / 'invalid.json'
        for content in (None, 'broken', '[]', '{"vid":"10000","pid":"1025"}',
                        '{"vid":"1915"}', '{"vid":"1915","pid":"1025","path":[]}'):
            if content is not None:
                invalid.write_text(content, encoding='utf-8')
            with self.subTest(content=content), patch.object(led, 'native') as native:
                code, _, err = self.cli('--config', invalid, 'led', 'send', 'busy', '--yes')
                self.assertEqual(code, 1)
                self.assertIn('Invalid device configuration', err)
                native.assert_not_called()

    def test_explicit_parameters_override_config_and_legacy_selection_survives(self):
        with patch.object(led, 'execute', return_value=0) as execute:
            self.assertEqual(self.cli('--config', self.configs[1], 'led', 'list', '--vid', 'ABCD',
                                      '--pid', 'FEDC', '--path', 'override')[0], 0)
            args = execute.call_args.args[0]
            self.assertEqual((args.vid, args.pid, args.path), (0xABCD, 0xFEDC, 'override'))
            with patch.object(Path, 'home', return_value=self.home):
                self.assertEqual(self.cli('led', 'list')[0], 0)
                self.assertEqual(execute.call_args.args[0].path, 'workbuddy-device')
        worker = SimpleNamespace(worker=True, vid=0x1234, pid=0x5678, path=None)
        with patch.object(led, 'read_config', side_effect=AssertionError('worker reread unrelated defaults')):
            led.resolve_device(worker)
        self.assertIsNone(worker.path)

    def test_parsing_reads_no_device_configuration(self):
        with patch.object(led, 'read_config', side_effect=AssertionError('parser read device configuration')):
            for argv in (('--help',), ('remote', 'status', '--help'), ('key', 'push', '--help')):
                self.assertEqual(self.cli(*argv)[0], 0)

    def test_status_reads_each_install_file_once_and_exposes_config(self):
        with patch.object(setup, 'usable_python', return_value=True), \
             patch.object(sys, 'platform', 'win32'), contextlib.redirect_stdout(io.StringIO()):
            setup.operate('install', True, self.home, agent='codex')
        with patch.object(Path, 'home', return_value=self.home), \
             patch.object(led, 'read_config', side_effect=AssertionError('status read device defaults')), \
             patch.object(setup, 'load', wraps=setup.load) as load:
            code, out, err = self.cli('remote', 'status', '--agent', 'codex')
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertIsInstance(result['config'], str)
        self.assertEqual(Path(result['config']), self.configs[1])
        paths = [call.args[0] for call in load.call_args_list]
        self.assertEqual(len(paths), 3)
        self.assertEqual(len(set(paths)), 3)
        with patch.object(setup, 'doctor', return_value=0) as doctor, \
             patch.object(setup, 'load', side_effect=AssertionError('doctor dispatched after write preparation')):
            self.assertEqual(setup.operate('doctor', home=self.home, agent='codex'), 0)
            doctor.assert_called_once()
