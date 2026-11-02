"""The plugin was called `adyusuf` until 02/11/2026: its files and variables keep working under the new name `podium`
(rule #4). Every test points HOME at a temporary folder, so no real file is read or written.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)
_spec = importlib.util.spec_from_file_location('podium_layers', os.path.join(SCRIPTS, 'podium_layers.py'))
layers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layers)

NAMES = ('PODIUM_CONFIG_USER', 'ADYUSUF_CONFIG_USER', 'PODIUM_STATUS_DIR', 'ADYUSUF_STATUS_DIR', 'PODIUM_SESSION_DIR',
         'ADYUSUF_SESSION_DIR', 'PODIUM_SEEN_DIR', 'ADYUSUF_SEEN_DIR')


class LegacyNames(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.home, '.claude'))
        self.saved = {name: os.environ.pop(name, None) for name in NAMES + ('HOME',)}
        os.environ['HOME'] = self.home

    def tearDown(self):
        for name, value in self.saved.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value

    def test_the_users_older_settings_file_is_copied_to_the_new_name_once_and_then_the_new_one_is_used(self):
        older = os.path.join(self.home, '.claude', 'adyusuf.json')
        with open(older, 'w', encoding='utf-8') as handle:
            json.dump({'mode': 'B'}, handle)
        path = layers.user_file()
        self.assertEqual(os.path.join(self.home, '.claude', 'podium.json'), path)
        with open(path, encoding='utf-8') as handle:
            self.assertEqual({'mode': 'B'}, json.load(handle))
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump({'mode': 'D'}, handle)
        self.assertEqual(path, layers.user_file())                        # not copied over again
        with open(path, encoding='utf-8') as handle:
            self.assertEqual({'mode': 'D'}, json.load(handle))

    def test_without_any_file_the_new_name_is_used_and_nothing_is_made(self):
        self.assertEqual(os.path.join(self.home, '.claude', 'podium.json'), layers.user_file())
        self.assertEqual([], os.listdir(os.path.join(self.home, '.claude')))

    def test_the_older_environment_variables_still_steer_where_the_files_are(self):
        os.environ['ADYUSUF_CONFIG_USER'] = os.path.join(self.home, 'mine.json')
        self.assertEqual(os.path.join(self.home, 'mine.json'), layers.user_file())
        os.environ['PODIUM_CONFIG_USER'] = os.path.join(self.home, 'new.json')
        self.assertEqual(os.path.join(self.home, 'new.json'), layers.user_file())    # the new name wins
        status = os.path.join(self.home, 'st')
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'podium_status.py'), '--session', 's-1', 'now', 'x'],
                              env=dict(os.environ, ADYUSUF_STATUS_DIR=status), capture_output=True, text=True)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(['s-1.json'], [name for name in os.listdir(status) if name.endswith('.json')])

    def test_a_copy_that_cannot_be_written_leaves_the_older_file_in_use(self):
        older = os.path.join(self.home, '.claude', 'adyusuf.json')
        with open(older, 'w', encoding='utf-8') as handle:
            json.dump({'mode': 'B'}, handle)
        os.chmod(os.path.join(self.home, '.claude'), 0o500)               # the folder cannot take a new file
        try:
            self.assertEqual(older, layers.user_file())
            self.assertEqual(['adyusuf.json'], os.listdir(os.path.join(self.home, '.claude')))
        finally:
            os.chmod(os.path.join(self.home, '.claude'), 0o700)

    def test_the_older_session_seen_and_settings_variables_are_read(self):
        script = os.path.join(SCRIPTS, 'podium_config.py')
        env = dict(os.environ, ADYUSUF_SESSION_DIR=os.path.join(self.home, 'ses'), ADYUSUF_SEEN_DIR=os.path.join(self.home, 'seen'),
                   ADYUSUF_CONFIG_USER=os.path.join(self.home, 'mine.json'))
        subprocess.run([sys.executable, script, 'set', 'mode', 'B', '--session', 's-1'], env=env, check=True, capture_output=True)
        self.assertEqual(['s-1.json'], os.listdir(os.path.join(self.home, 'ses')))
        subprocess.run([sys.executable, script, 'set', 'mode', 'D'], env=env, check=True, capture_output=True)
        self.assertTrue(os.path.isfile(os.path.join(self.home, 'mine.json')))
        subprocess.run([sys.executable, script, 'notify', 'UserPromptSubmit'], env=env, input='{"session_id": "s-1"}',
                       text=True, check=True, capture_output=True)
        self.assertEqual(['s-1'], os.listdir(os.path.join(self.home, 'seen')))
        subprocess.run([sys.executable, script, 'set', 'ci.runner', 'self-hosted'], env=env, check=True, capture_output=True)
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'sdlc_settings.py'), 'show'], env=env, capture_output=True, text=True)
        self.assertIn('"runner": "self-hosted"', done.stdout)            # sdlc_settings reads the older variable too

    def test_the_older_settings_files_count_as_bookkeeping_for_the_steps_guard(self):
        guard = lambda path: subprocess.run(       # noqa: E731
            [sys.executable, os.path.join(SCRIPTS, 'podium_status.py'), 'hook', 'guard'], capture_output=True,
            env=dict(os.environ, HOME='/work/home', PODIUM_STATUS_DIR=os.path.join(self.home, 'st')),     # a home outside temp
            input=json.dumps({'session_id': 's-1', 'tool_name': 'Write', 'tool_input': {'file_path': path}}).encode()).returncode
        self.assertEqual(0, guard('/work/home/.claude/adyusuf.json'))
        self.assertEqual(2, guard('/work/home/.claude/dev-mods/x/register.tsx'))           # code under ~/.claude is work
        self.assertEqual(0, guard('/work/repo/.claude/adyusuf.json'))
        self.assertEqual(2, guard('/work/repo/src/app.py'))

    def test_a_projects_older_settings_file_is_read_while_it_is_the_only_one(self):
        repo = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', repo], check=True)
        os.makedirs(os.path.join(repo, '.claude'))
        older = os.path.join(repo, '.claude', 'adyusuf.json')
        with open(older, 'w', encoding='utf-8') as handle:
            json.dump({'mode': 'A'}, handle)
        here = os.getcwd()
        try:
            os.chdir(repo)
            self.assertEqual(os.path.realpath(older), os.path.realpath(layers.project_file()))
            with open(os.path.join(repo, '.claude', 'podium.json'), 'w', encoding='utf-8') as handle:
                json.dump({'mode': 'B'}, handle)
            self.assertTrue(layers.project_file().endswith(os.path.join('.claude', 'podium.json')))
        finally:
            os.chdir(here)


if __name__ == '__main__':
    unittest.main()
