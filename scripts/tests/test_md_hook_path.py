"""scripts/md_hook_path.py — md-hook.sh's payload reader: the edited file's path, or '' for the Stop event."""
import os
import subprocess
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)
from md_hook_path import edited_path  # noqa: E402


class EditedPath(unittest.TestCase):
    def test_file_path_wins_then_path(self):
        self.assertEqual('/r/CLAUDE.md', edited_path('{"tool_input": {"file_path": "/r/CLAUDE.md", "path": "/x"}}'))
        self.assertEqual('/r/x.md', edited_path('{"tool_input": {"path": "/r/x.md"}}'))

    def test_a_stop_payload_or_a_bad_one_gives_nothing(self):
        for text in ('{"session_id": "s"}', 'not json', '', '[1]', '{"tool_input": "x"}', '{"tool_input": {"file_path": null}}'):
            self.assertEqual('', edited_path(text), text)

    def test_the_script_prints_it(self):
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'md_hook_path.py')], capture_output=True, text=True,
                              input='{"tool_input": {"file_path": "/r/CLAUDE.md"}}')
        self.assertEqual(('/r/CLAUDE.md\n', 0), (done.stdout, done.returncode))


if __name__ == '__main__':
    unittest.main()
