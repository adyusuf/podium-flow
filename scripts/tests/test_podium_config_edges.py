"""scripts/podium_config.py at its edges (test inventory, 14/11/2026): a hand-edited file that cannot be written back
(F-027), a dropped layer that is said instead of hidden (F-028), and the set/apply/unset paths the inventory found
untested. Every test goes through the command line.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_podium_config as base  # noqa: E402


class ScalarWhereAGroupBelongs(base.Tool):
    """F-027: {"push": true} written by hand ended `set push.prod no` in a TypeError traceback."""

    def refused(self, path, text, *args, stdin=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        _, err, code = self.run_tool(*args, stdin=stdin)
        self.assertEqual(1, code, err)
        self.assertNotIn('Traceback', err)
        self.assertIn('refusing to write', err)
        self.assertIn("'push'" if 'push' in text else "'mode'", err)
        with open(path, encoding='utf-8') as handle:
            self.assertEqual(text, handle.read())                      # untouched
        self.assertEqual([], [name for name in os.listdir(os.path.dirname(path)) if name.endswith('.tmp')])

    def test_set_unset_and_apply_refuse_with_exit_1_and_leave_the_file_as_it_was(self):
        text = '{"push": true}'
        self.refused(self.user, text, 'set', 'push.prod', 'no')
        self.refused(self.user, text, 'unset', 'push.prod')
        self.refused(self.user, text, 'apply', '-', stdin=json.dumps({'push.prod': False}))
        self.refused(self.project, text, 'set', 'push.prod', 'no', '--project')
        self.refused(os.path.join(self.home, 'sessions', 's1.json'), text, 'set', 'push.prod', 'no', '--session', 's1')

    def test_a_group_where_a_single_value_belongs_is_refused_too(self):
        self.refused(self.user, '{"mode": {"x": 1}}', 'set', 'mode', 'B')

    def test_reading_such_a_file_still_works_and_says_what_is_ignored(self):
        # The rest of the file still counts; the misshapen value is left out and said on stderr (QA 16/11/2026).
        for text, said in (('{"push": true, "mode": "B"}', 'push is a group of settings'),
                           ('{"mode": "B", "push": {"prod": false}, "agents": {"qa": {"x": 1}}}', None)):
            with self.subTest(text=text):
                with open(self.user, 'w', encoding='utf-8') as handle:
                    handle.write(text)
                out, err, code = self.run_tool('get', 'mode')
                self.assertEqual(('B\n', 0), (out, code))
                if said:
                    self.assertIn(said, err)
                    self.assertIn('this value is ignored', err)

    def test_a_group_where_one_value_belongs_is_said_on_reading(self):
        with open(self.user, 'w', encoding='utf-8') as handle:
            handle.write('{"mode": {"x": 1}, "push": {"prod": false}}')
        out, err, code = self.run_tool('get', 'push.prod')
        self.assertEqual(('no\n', 0), (out, code))
        self.assertIn('mode is one value, not a group - mode.x is ignored', err)


class DroppedLayerIsSaid(base.Tool):
    """F-028: a layer with one bad value is not trusted as a whole (never half a project file), and that is now said."""

    def setUp(self):
        super().setUp()
        self.run_tool('set', 'push.prod', 'no')                         # the user's value
        os.makedirs(os.path.dirname(self.project))
        with open(self.project, 'w', encoding='utf-8') as handle:
            json.dump({'push': {'prod': 'maybe'}, 'mode': 'B'}, handle)

    def test_get_prints_the_dropped_layer_on_stderr_and_still_answers(self):
        for key, answer in (('push.prod', 'no\n'), ('mode', 'C\n')):     # the project's good `mode` goes with it
            out, err, code = self.run_tool('get', key)
            self.assertEqual((0, answer), (code, out), key)
            self.assertIn(os.path.join('.claude', 'podium.json'), err)
            self.assertIn('the whole file is ignored', err)
            self.assertTrue(err.startswith('! '), err)

    def test_show_and_context_carry_the_problem(self):
        data = json.loads(self.run_tool('show', '--json')[0])
        self.assertEqual((False, 'user'), (data['values']['push.prod'], data['sources']['push.prod']))
        self.assertEqual(1, len(data['problems']))
        self.assertIn('the whole file is ignored', data['problems'][0])
        self.assertIn('! ', self.run_tool('show')[0])
        self.assertIn('the whole file is ignored', self.run_tool('show')[0])
        self.assertIn('  ! ', self.run_tool('context')[0])

    def test_a_clean_get_prints_nothing_on_stderr(self):
        os.remove(self.project)
        self.assertEqual(('no\n', '', 0), self.run_tool('get', 'push.prod'))


class SetApplyUnset(base.Tool):
    def stored(self, path):
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)

    def test_set_steps_enforce_force_stores_block(self):
        self.run_tool('set', 'steps.enforce', 'remind')
        out, err, code = self.run_tool('set', 'steps.enforce', 'force')
        self.assertEqual(0, code, err)
        self.assertIn('steps.enforce = block', out)
        self.assertEqual({'steps': {'enforce': 'block'}}, self.stored(self.user))
        self.assertEqual('block\n', self.run_tool('get', 'steps.enforce')[0])

    def test_apply_from_stdin_writes_the_chosen_layer(self):
        out, err, code = self.run_tool('apply', '-', '--project', stdin=json.dumps({'push': {'dev': False}, 'mode': 'D'}))
        self.assertEqual(0, code, err)
        self.assertIn('2 setting(s) written to %s' % os.path.realpath(self.project), out)
        self.assertEqual({'mode': 'D', 'push': {'dev': False}}, self.stored(self.project))
        self.assertFalse(os.path.exists(self.user))

    def test_apply_from_a_file(self):
        source = os.path.join(self.home, 'in.json')
        with open(source, 'w', encoding='utf-8') as handle:
            json.dump({'merge.prod': False}, handle)
        self.assertEqual(0, self.run_tool('apply', source)[2])
        self.assertEqual({'merge': {'prod': False}}, self.stored(self.user))

    def test_apply_from_a_missing_file_is_exit_1_and_writes_nothing(self):
        _, err, code = self.run_tool('apply', os.path.join(self.home, 'no-such.json'))
        self.assertEqual(1, code, err)
        self.assertIn('no-such.json', err)
        self.assertNotIn('Traceback', err)
        self.assertFalse(os.path.exists(self.user))

    def test_apply_of_text_that_is_not_utf_8_is_exit_1_and_writes_nothing(self):
        # F-047 (found in phase 2): a file in a legacy code page ended in a UnicodeDecodeError traceback.
        text = '{"mode": "B", "note": "\u015fi\u015fman"}'.encode('cp1254')
        source = os.path.join(self.home, 'cp1254.json')
        with open(source, 'wb') as handle:
            handle.write(text)
        env = dict(os.environ, PODIUM_CONFIG_USER=self.user, PODIUM_SESSION_DIR=os.path.join(self.home, 'sessions'))
        for argument, stdin in ((source, None), ('-', text)):           # from a file and from stdin
            result = subprocess.run(['python3', os.path.join(base.SCRIPTS, 'podium_config.py'), 'apply', argument],
                                    cwd=self.repo, capture_output=True, env=env, input=stdin)
            err = result.stderr.decode('utf-8', 'replace')
            self.assertEqual(1, result.returncode, err)
            self.assertNotIn('Traceback', err)
            self.assertIn('not UTF-8', err)
        self.assertFalse(os.path.exists(self.user))

    def test_unset_on_the_project_and_the_user_layer_removes_only_that_key(self):
        self.run_tool('set', 'push.prod', 'no')
        self.run_tool('set', 'mode', 'B')
        self.run_tool('set', 'push.prod', 'yes', '--project')
        self.run_tool('set', 'merge.dev', 'no', '--project')
        out, err, code = self.run_tool('unset', 'push.prod', '--project')
        self.assertEqual((0, 'push.prod removed from %s\n' % os.path.realpath(self.project)), (code, out), err)
        self.assertEqual({'merge': {'dev': False}}, self.stored(self.project))
        self.assertEqual('no\n', self.run_tool('get', 'push.prod')[0])            # the user's value shows through
        out, err, code = self.run_tool('unset', 'push.prod')
        self.assertEqual((0, 'push.prod removed from %s\n' % self.user), (code, out), err)
        self.assertEqual({'mode': 'B'}, self.stored(self.user))
        self.assertEqual('yes\n', self.run_tool('get', 'push.prod')[0])           # back to the default
        self.assertEqual(0, self.run_tool('unset', 'push.prod')[2])               # a key the file lacks: nothing to do
        self.assertEqual({'mode': 'B'}, self.stored(self.user))


if __name__ == '__main__':
    unittest.main()
