"""scripts/podium_config.py notify: the hook that tells a running session a setting changed.

Moved out of test_podium_config.py (14/11/2026, F-032): test_podium_session.py inherited the whole class to reuse its
helper, so every test here ran twice. The helper is NotifyTool now; the tests run once.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_podium_config as base  # noqa: E402

SCRIPTS = base.SCRIPTS


class NotifyTool(base.Tool):
    """The hook run through its real command line, with its own seen-folder."""

    def setUp(self):
        super().setUp()
        self.seen = os.path.join(self.home, 'seen')

    def hook(self, session='sess-1', event='UserPromptSubmit'):
        env = dict(os.environ, PODIUM_CONFIG_USER=self.user, PODIUM_SEEN_DIR=self.seen,
                   PODIUM_SESSION_DIR=os.path.join(self.home, 'sessions'))
        result = subprocess.run(['python3', os.path.join(SCRIPTS, 'podium_config.py'), 'notify', event], cwd=self.repo,
                                capture_output=True, text=True, env=env, input=json.dumps({'session_id': session}))
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)['hookSpecificOutput'] if result.stdout.strip() else None


class Notify(NotifyTool):
    """The next task sees a change, the current one is not split."""

    def test_the_first_call_of_a_session_says_nothing_it_only_remembers(self):
        self.assertIsNone(self.hook())

    def test_a_seen_file_that_still_holds_a_retired_key_is_not_a_change(self):
        # A session that started before the retirement recorded the two monitor keys: that alone is not a change.
        self.hook()
        path = os.path.join(self.seen, 'sess-1')
        with open(path, encoding='utf-8') as handle:
            seen = json.load(handle)
        seen.update({'monitor.connect': True, 'monitor.message_format': 'short'})
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(seen, handle)
        self.assertIsNone(self.hook())

    def test_an_unchanged_configuration_stays_silent(self):
        self.hook()
        self.assertIsNone(self.hook())
        self.assertIsNone(self.hook(event='PostToolUse'))

    def test_a_change_is_announced_once_with_what_changed_and_when_it_applies(self):
        self.hook()
        self.run_tool('set', 'push.prod', 'no')
        self.run_tool('set', 'agents.qa.model', 'haiku')
        note = self.hook(event='PostToolUse')
        self.assertEqual('PostToolUse', note['hookEventName'])
        text = note['additionalContext']
        self.assertIn('push.prod: yes -> no', text)
        self.assertIn('agents.qa.model: default -> haiku', text)
        self.assertIn('NEXT task', text)                       # applies from the next task...
        self.assertIn('Reply length is the exception: it applies from your next reply.', text)
        self.assertIn('do not restart or split', text)         # ...and never splits the one running
        self.assertIn('qa (haiku)', text)                      # the new effective picture is attached
        self.assertIsNone(self.hook(event='PostToolUse'))      # once

    def test_each_session_is_told_separately(self):
        self.hook('a')
        self.hook('b')
        self.run_tool('set', 'mode', 'D')
        self.assertIsNotNone(self.hook('a'))
        self.assertIsNotNone(self.hook('b'))
        self.assertIsNone(self.hook('a'))

    def test_a_project_layer_change_is_noticed_too(self):
        self.hook()
        self.run_tool('set', 'mode', 'B', '--project')
        self.assertIn('mode: C -> B', self.hook()['additionalContext'])

    def test_a_broken_payload_or_file_never_fails_the_hook(self):
        env = dict(os.environ, PODIUM_CONFIG_USER=self.user, PODIUM_SEEN_DIR=self.seen)
        for payload in ('', 'not json', '{"session_id": "../../etc"}'):
            result = subprocess.run(['python3', os.path.join(SCRIPTS, 'podium_config.py'), 'notify', 'UserPromptSubmit'],
                                    cwd=self.repo, capture_output=True, text=True, env=env, input=payload)
            self.assertEqual((0, ''), (result.returncode, result.stdout), payload)
        with open(self.user, 'w', encoding='utf-8') as handle:
            handle.write('{ broken')
        self.assertEqual(0, subprocess.run(['python3', os.path.join(SCRIPTS, 'podium_config.py'), 'notify', 'PostToolUse'],
                                           cwd=self.repo, capture_output=True, text=True, env=env,
                                           input=json.dumps({'session_id': 's'})).returncode)

    def test_settings_a_session_never_saw_are_not_a_change(self):
        # Found by QA: after /plugin update a running session's seen-file lacks the new keys, so the first call listed all
        # of them as "None -> value" although the user changed nothing.
        self.hook()
        seen = os.path.join(self.seen, 'sess-1')
        with open(seen, encoding='utf-8') as handle:
            values = json.load(handle)
        for key in [k for k in values if k.startswith(('ci_after_push', 'e2e_before_deploy', 'pod.', 'gates_before_push'))]:
            del values[key]
        values['monitor.connect'] = True                                  # and a retired key the old script wrote
        with open(seen, 'w', encoding='utf-8') as handle:
            json.dump(values, handle)
        self.assertIsNone(self.hook())
        with open(seen, encoding='utf-8') as handle:
            self.assertIn('pod.connect', json.load(handle))               # remembered silently
        self.run_tool('set', 'push.prod', 'no')
        note = self.hook()
        self.assertIn('push.prod: yes -> no', note['additionalContext'])
        self.assertNotIn('pod.connect', note['additionalContext'].split('\n')[0])

    def test_an_id_the_session_layer_refuses_never_gets_a_seen_file(self):
        # F-032: notify kept its own copy of the id rule without the length cap, so a 300-character id was accepted here
        # while the session layer refused it. One rule now: podium_session.valid.
        for session in ('x' * 101, 'x' * 300, 'a.b', 'a b'):
            self.assertIsNone(self.hook(session))
        self.assertFalse(os.path.exists(self.seen) and os.listdir(self.seen))
        self.assertIsNone(self.hook('x' * 100))                 # the longest id the session layer takes still works
        self.assertEqual(['x' * 100], os.listdir(self.seen))

    def test_the_seen_file_is_replaced_whole_and_leaves_no_temporary_file(self):
        # F-032: a reader (the next hook call) never sees a half-written seen-file: a temporary file is renamed over it.
        self.hook()
        path = os.path.join(self.seen, 'sess-1')
        before = os.stat(path).st_ino
        self.run_tool('set', 'push.prod', 'no')
        self.assertIn('push.prod: yes -> no', self.hook()['additionalContext'])
        self.assertNotEqual(before, os.stat(path).st_ino)       # a new file took its place (os.replace)
        self.assertEqual(['sess-1'], os.listdir(self.seen))
        with open(path, encoding='utf-8') as handle:
            self.assertIs(json.load(handle)['push.prod'], False)


if __name__ == '__main__':
    unittest.main()
