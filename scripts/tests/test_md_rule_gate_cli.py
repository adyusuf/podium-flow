"""md-rule-gate.py through its command line: a file it cannot read.

A missing or non-UTF-8 file ended in a Python traceback. It now exits 2 with a one-line message and the
gate counts as closed. Split from test_md_rule_gate.py, which sits at the 300-line limit (#9); these tests
run the real script, not main().
"""
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
GATE = os.path.join(SCRIPTS, 'md-rule-gate.py')


class AFileItCannotRead(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.good = os.path.join(self.dir.name, 'good.md')
        with open(self.good, 'w', encoding='utf-8') as handle:
            handle.write('Every endpoint must check authorization.\n')

    def run_gate(self, *args):
        done = subprocess.run([sys.executable, GATE, *args], capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def assert_closed_without_a_traceback(self, code, out, expected):
        self.assertEqual(2, code, out)
        self.assertIn(expected, out)
        self.assertIn('the gate counts as closed', out)
        self.assertNotIn('Traceback', out)

    def test_a_missing_old_file(self):
        missing = os.path.join(self.dir.name, 'no-such-old.md')
        code, out = self.run_gate(missing, self.good)
        self.assert_closed_without_a_traceback(code, out, missing)

    def test_a_missing_new_file(self):
        missing = os.path.join(self.dir.name, 'no-such-new.md')
        code, out = self.run_gate(self.good, missing)
        self.assert_closed_without_a_traceback(code, out, missing)

    def test_a_file_that_is_not_utf8(self):
        binary = os.path.join(self.dir.name, 'binary.md')
        with open(binary, 'wb') as handle:
            handle.write(b'\xff\xfe\x00rule')
        code, out = self.run_gate(binary, self.good)
        self.assert_closed_without_a_traceback(code, out, 'not UTF-8')

    def test_no_file_argument_prints_the_usage(self):
        code, out = self.run_gate(self.good)
        self.assertEqual(2, code, out)
        self.assertIn('Usage', out)
        self.assertNotIn('Traceback', out)


if __name__ == '__main__':
    unittest.main()
