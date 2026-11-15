"""The pre-commit hook's install mode and its behaviour outside a repository (scripts/pre-commit.sh) - moved
verbatim out of test_pre_commit_steps.py so both files stay under the 300-line limit (rule #9). The fixture (Hook)
stays there.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pre_commit_steps import HOOK, Hook  # noqa: E402


class Install(Hook):
    def test_install_links_the_hooks_into_git(self):
        self.script('scripts/pre-commit.sh', '#!/usr/bin/env bash\nexit 0\n')
        self.script('scripts/commit-msg.sh', '#!/usr/bin/env bash\nexit 0\n')
        out, code = self.run_hook('--install')
        self.assertEqual(0, code, out)
        for hook in ('pre-commit', 'commit-msg'):
            path = os.path.join(self.root, '.git', 'hooks', hook)
            self.assertTrue(os.path.islink(path), f'{hook} was not linked')

    def test_install_without_a_commit_msg_script_still_links_pre_commit(self):
        self.script('scripts/pre-commit.sh', '#!/usr/bin/env bash\nexit 0\n')
        out, code = self.run_hook('--install')
        self.assertEqual(0, code, out)
        self.assertTrue(os.path.islink(os.path.join(self.root, '.git', 'hooks', 'pre-commit')))


class OutsideARepository(Hook):
    def test_it_passes_quietly(self):
        loose = tempfile.mkdtemp()
        try:
            result = subprocess.run(['bash', HOOK], cwd=loose, capture_output=True, text=True,
                                    env=dict(os.environ, HOME=self.home))
            self.assertEqual(0, result.returncode)
        finally:
            shutil.rmtree(loose, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
