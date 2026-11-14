"""The bypasses of the destructive-command guard found by the test inventory (14/11/2026, F-001 and F-002), as one table.

Each row runs twice: through `verdict()` in scripts/guard-inspect.py (the reason it gives) and through the real hook,
`bash scripts/guard-destructive.sh` with a PreToolUse payload on stdin (the exit code the harness reads). The wrapper run
matters on its own: its grep prefilter decides what reaches the inspector at all, and `git commit -n` carried none of its
keywords until `commit` was added.

The NEAR MISSES are the other half: the widened patterns must not start refusing ordinary work. A push to prod stays
not judged (the configuration decides, 17/10/2026). The ALLOWED table of test_guard_destructive.py still runs there.

A file of its own because test_guard_destructive.py is at the 300-line limit (#9). Written with the Write tool, not a
shell heredoc: the live hook would refuse a heredoc quoting these commands.
"""
import importlib.util
import json
import os
import subprocess
import unittest

SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
GUARD = os.path.join(SCRIPTS, 'guard-destructive.sh')
_spec = importlib.util.spec_from_file_location('guard_inspect', os.path.join(SCRIPTS, 'guard-inspect.py'))
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

# (command, a fragment of the reason verdict() must give)
BYPASSES = [
    # forced push: a bundled -f, a + refspec, the lease with its value
    ('git push -fu origin dev', 'forced push'),
    ('git push -uf origin dev', 'forced push'),
    ('git push origin +dev', 'forced push'),
    ('git push origin +HEAD:feature/x', 'forced push'),
    ("git push origin '+dev'", 'forced push'),
    ('git push --force-with-lease=dev:abc123 origin dev', 'forced push'),
    # git global options before the verb, for all three git rules
    ('git -C ../repo push --force origin dev', 'forced push'),
    ('git -C "my repo" push -f origin dev', 'forced push'),
    ('git -c push.default=current push -f', 'forced push'),
    ('git --git-dir=/srv/r push --force', 'forced push'),
    ('git --work-tree /srv/w push -f', 'forced push'),
    ('git -C repo push origin main', 'straight to main'),
    ('git -C repo commit --no-verify -m x', 'gitleaks'),
    ('git -c core.editor=true merge --no-verify feature/x', 'gitleaks'),
    # mirror and deletion
    ('git push --mirror', 'mirror'),
    ('git push --mirror origin', 'mirror'),
    ('git push --delete origin feature/x', 'deletes a remote branch'),
    ('git push origin --delete feature/x', 'deletes a remote branch'),
    ('git push -d origin feature/x', 'deletes a remote branch'),
    ('git push origin :feature/x', 'deletes a remote branch'),
    # main by its full ref name
    ('git push origin refs/heads/main', 'straight to main'),
    ('git push origin HEAD:refs/heads/main', 'straight to main'),
    ('git push origin HEAD:main', 'straight to main'),
    # git commit -n is --no-verify, alone or in a bundle
    ('git commit -n -m x', '-n (--no-verify)'),
    ('git commit -an -m x', '-n (--no-verify)'),
    ('git commit -m x -n', '-n (--no-verify)'),
    ('git -c user.name=x commit -n', '-n (--no-verify)'),
    # rm: long options, split options, quoted targets
    ('rm --recursive --force /', 'recursive delete'),
    ('rm --force --recursive .', 'recursive delete'),
    ('rm -r -f /', 'recursive delete'),
    ('rm -f -r ~', 'recursive delete'),
    ('rm -rf --no-preserve-root /', 'recursive delete'),
    ('rm -rf "$HOME"', 'recursive delete'),
    ('rm -rf "${HOME}"', 'recursive delete'),
    ('rm -rf "~"', 'recursive delete'),
    ("rm -rf '/'", 'recursive delete'),
    ('rm -R -- "$HOME"', 'recursive delete'),
    # F-002: a here-string is not a heredoc, so the next line is still judged
    ('cat <<<foo\ngit push --force', 'forced push'),
    ('cat <<< foo\ngit push origin main', 'straight to main'),
]

NEAR_MISSES = [
    'git push -u origin dev', 'git push -n origin dev', 'git push origin prod', 'git -C repo push origin prod',
    'git -C ../repo push origin dev', 'git push origin feature/main', 'git push origin feature/x-fix',
    'git push origin feature/remove-d', 'git -c push.default=current fetch origin main',
    'git commit -m "wip"', 'git commit -am "wip"', 'git commit --amend --no-edit', 'git -C repo commit -m x',
    'git merge -n feature/x', 'rm -rf ./build', 'rm --recursive build', 'rm -r -f node_modules', 'rm -f /tmp/x.log',
    'rm -rf "$HOME/tmp/x"', 'cat <<<foo',
]


def wrapper(command):
    payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': command}})
    done = subprocess.run(['bash', GUARD], input=payload, capture_output=True, text=True)
    return done.returncode, done.stderr


class Bypasses(unittest.TestCase):
    def test_each_bypass_gets_its_reason_from_the_inspector(self):
        for command, reason in BYPASSES:
            with self.subTest(command=command):
                self.assertIn(reason, guard.verdict(command) or 'NOT blocked')

    def test_each_bypass_is_blocked_by_the_real_hook(self):
        for command, reason in BYPASSES:
            with self.subTest(command=command):
                code, err = wrapper(command)
                self.assertEqual(2, code, err)
                self.assertIn(reason, err)

    def test_the_near_misses_stay_allowed_in_both(self):
        for command in NEAR_MISSES:
            with self.subTest(command=command):
                self.assertIsNone(guard.verdict(command))
                self.assertEqual((0, ''), wrapper(command))


if __name__ == '__main__':
    unittest.main()
