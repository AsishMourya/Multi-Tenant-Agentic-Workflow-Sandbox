import os
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == 'posix' and getattr(os, 'geteuid', lambda: 1)() == 0,
                     'guest process limits require Linux root')
class GuestRuntimeTests(unittest.TestCase):
    def setUp(self):
        from sandbox import guest_runtime
        self.runtime = guest_runtime
        self.tmp = tempfile.TemporaryDirectory(dir='/tmp')
        Path(self.tmp.name).chmod(0o755)
        self.source = Path(self.tmp.name) / 'submission.py'
        self.original = guest_runtime.SOURCE
        guest_runtime.SOURCE = str(self.source)
        self.settings = {'cpu_seconds': 2, 'address_bytes': 128 * 1024 * 1024,
                         'processes': 8, 'output_bytes': 4096, 'wall_seconds': 2}

    def tearDown(self):
        self.runtime.SOURCE = self.original
        self.tmp.cleanup()

    def test_unprivileged_output_and_timeout(self):
        self.source.write_text('import os, json, sys\n'
                               'print(json.dumps({"uid":os.geteuid(),"input":json.load(sys.stdin)}))\n')
        self.source.chmod(0o644)
        result = self.runtime.execute(self.settings, {'value': 42})
        self.assertEqual(result['status'], 'ok')
        self.assertIn('"uid": 65534', result['stdout'])
        self.assertIn('"value": 42', result['stdout'])
        self.source.write_text('while True: pass\n')
        result = self.runtime.execute(self.settings, {})
        self.assertNotEqual(result['status'], 'ok')

    def test_console_reader_preserves_next_event(self):
        from scripts.firecracker_probe import Guest
        reader, writer = os.pipe()
        try:
            guest = object.__new__(Guest)
            guest.master = reader
            guest.transcript = bytearray()
            guest.pending = bytearray()
            os.write(writer, b'FIRST\r\nSECOND\r\n')
            first, event = guest.read_until_any(('FIRST\n', 'SECOND\n'), timeout=1)
            self.assertEqual((first, event), ('FIRST\n', 'FIRST\n'))
            self.assertEqual(guest.read_until('SECOND\n', timeout=1), 'SECOND\n')
        finally:
            os.close(reader)
            os.close(writer)

    def test_memory_and_output_limits(self):
        self.source.write_text('x = bytearray(512 * 1024 * 1024)\n')
        self.source.chmod(0o644)
        memory = self.runtime.execute(self.settings, {})
        self.assertEqual(memory['status'], 'error')
        self.assertIn('MemoryError', memory['stderr'])
        self.source.write_text('print("x" * 10000)\n')
        output = self.runtime.execute(self.settings, {})
        self.assertEqual(output['status'], 'output_limit')

    def test_process_limit(self):
        self.source.write_text(
            'import json, subprocess\n'
            'children=[]\nblocked=False\n'
            'try:\n'
            '    for _ in range(32): children.append(subprocess.Popen(["sleep", "1"]))\n'
            'except OSError: blocked=True\n'
            'finally:\n'
            '    for child in children: child.terminate()\n'
            '    for child in children: child.wait()\n'
            'print(json.dumps({"blocked":blocked,"started":len(children)}))\n')
        self.source.chmod(0o644)
        result = self.runtime.execute(self.settings, {})
        self.assertEqual(result['status'], 'ok')
        self.assertIn('"blocked": true', result['stdout'])


if __name__ == '__main__':
    unittest.main()
