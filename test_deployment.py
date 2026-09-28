"""Verify provisioning arguments without contacting LXD or touching hardware."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('build_vm', Path(__file__).parent/'deploy/lxd-vm/build_vm.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

class BuildTests(unittest.TestCase):
    def arguments(self):
        return ['build_vm.py', '--name', 'portable-lab', '--host-ip', '192.0.2.10',
                '--guest-ip', '10.42.0.20', '--network', 'custom-bridge', '--pool', 'custom-pool',
                '--lab-mac', '02:00:00:00:00:01', '--target', '02:00:00:00:00:02',
                '--allow-client', '192.0.2.99', '--panel-port', '9875', '--speed-port', '9876']

    def output(self, *args):
        if args == ('lxc', 'list', '--format=json'): return '[]'
        if args[:3] == ('lxc', 'network', 'get'):
            return '10.42.0.1/24' if args[-1] == 'ipv4.address' else 'true'
        if args[:3] == ('lxc', 'network', 'list-leases'): return '[]'
        if args[:3] == ('lxc', 'storage', 'show'): return 'pool exists'
        if args[-1] == '--porcelain': return ''
        if args[-2:] == ('rev-parse', 'HEAD'): return 'a'*40
        if args[-2:] == ('uname', '-r'): return '6.8.0-test'
        raise AssertionError(args)

    def test_independent_host_and_ports(self):
        with patch('sys.argv', self.arguments()), patch.object(build, 'output', side_effect=self.output), \
             patch.object(build, 'run') as run, patch.object(build.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
            build.main()
        commands = [c.args for c in run.call_args_list]
        init = next(c for c in commands if c[:2] == ('lxc', 'init'))
        self.assertIn('--no-profiles', init)
        self.assertEqual(init[init.index('--network')+1], 'custom-bridge')
        self.assertEqual(init[init.index('--storage')+1], 'custom-pool')
        configure = next(c for c in commands if '/opt/easymesh-lab/deploy/lxd-vm/configure_guest.py' in c)
        self.assertEqual(configure[configure.index('--management-gateway')+1], '10.42.0.1')
        self.assertEqual(configure[configure.index('--panel-port')+1], '9875')
        self.assertNotIn('--nic-driver', configure)
        self.assertTrue(any('listen=tcp:192.0.2.10:9875' in c and 'connect=tcp:10.42.0.20:9875' in c for c in commands))
        self.assertFalse(any('usb' in c for c in commands))
        self.assertNotIn('rev120', repr(commands))
        self.assertNotIn('10.77.171.1', repr(commands))

    def test_existing_vm_never_modified(self):
        with patch('sys.argv', self.arguments()), patch.object(build, 'output', return_value='[{"name":"portable-lab"}]'), patch.object(build, 'run') as run:
            with self.assertRaises(SystemExit): build.main()
        run.assert_not_called()

    def test_overlapping_management_subnet_rejected(self):
        def output(*args):
            if args[-1] == 'ipv4.address': return '10.203.88.1/24'
            return self.output(*args)
        with patch('sys.argv', self.arguments()), patch.object(build, 'output', side_effect=output), patch.object(build, 'run') as run:
            with self.assertRaises(SystemExit): build.main()
        run.assert_not_called()

if __name__ == '__main__': unittest.main()
