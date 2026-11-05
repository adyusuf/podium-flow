"""The gate's step ticks as settings (user decision 02/11/2026): `gate_steps.<id>.<target>`, one per row of GATE_STEPS
in gate-lib.sh and target.

What matters:

  · every step starts on, with no file saying so: the default lives in the schema, so no second step list exists;
  · the layers work as for any setting: the user's saved choice comes back in a new session, the session beats it;
  · the session-start context names the unticked steps of a target whose gate is on (they are waived, rule #34);
  · the ticks reach the project's .claude/sdlc-settings.json, where the gate reads them.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_podium_config import SCRIPTS, Tool, cfg  # noqa: E402
os.environ.setdefault('PODIUM_SETTINGS_SOURCE', 'file')  # a developer's own live panel must not change a result (gate-lib-panel.sh)


class Ticks(Tool):
    def test_every_step_starts_on_for_every_target(self):
        values = self.values()['values']
        keys = [key for key in values if key.startswith('gate_steps.')]
        self.assertEqual(len(cfg.GATE_STEPS) * len(cfg.TARGETS), len(keys))
        self.assertTrue(all(values[key] is True for key in keys))

    def test_the_saved_choice_comes_back_in_a_new_session_and_the_session_beats_it(self):
        self.run_tool('set', 'gate_steps.compat.test', 'no')
        _, _, code = self.run_tool('set', '--session', 'one', 'gate_steps.lint.test', 'no')
        self.assertEqual(0, code)
        fresh, _, _ = self.run_tool('get', '--session', 'two', 'gate_steps.compat.test')
        self.assertEqual('no', fresh.strip())
        other, _, _ = self.run_tool('get', '--session', 'two', 'gate_steps.lint.test')
        self.assertEqual('yes', other.strip(), 'a session-only tick must not reach another session')
        self.run_tool('set', '--session', 'one', 'gate_steps.compat.test', 'yes')
        now, _, _ = self.run_tool('get', '--session', 'one', 'gate_steps.compat.test')
        self.assertEqual('yes', now.strip())

    def test_an_unknown_step_is_refused(self):
        _, err, code = self.run_tool('set', 'gate_steps.nonsense.dev', 'no')
        self.assertEqual(2, code)
        self.assertIn('unknown setting', err)

    def test_the_context_names_the_unticked_steps_where_the_gate_runs(self):
        self.run_tool('set', 'gate_steps.compat.test', 'no')
        self.run_tool('set', 'gate_steps.lint.dev', 'no')         # the dev gate is off by default: nothing to name
        out, _, _ = self.run_tool('context')
        line = next(text for text in out.splitlines() if text.strip().startswith('test: merge'))
        self.assertIn('gate steps off (waived, named in Gate-Waived): compat', line)   # the id the gate prints
        dev = next(text for text in out.splitlines() if text.strip().startswith('dev: merge'))
        self.assertNotIn('gate steps off', dev)

    def test_the_schema_gives_the_pane_each_steps_name_and_heading(self):
        out, _, _ = self.run_tool('schema')
        specs = [spec for spec in json.loads(out) if spec['key'].startswith('gate_steps.')]
        step, name, heading = cfg.GATE_STEPS[0]
        first = specs[0]
        self.assertEqual(('gate_steps.%s.dev' % step, name, heading, True, 'bool'),
                         (first['key'], first['step'], first['heading'], first['default'], first['type']))


class Locked(Tool):
    """The secret scan and SAST can never be unticked (user decision 02/11/2026, rule #19), at any layer."""

    def test_set_and_apply_refuse_to_turn_them_off_at_every_layer(self):
        for step in cfg.LOCKED_STEPS:
            for scope in ([], ['--project'], ['--session', 'one']):
                with self.subTest(step=step, scope=scope):
                    _, err, code = self.run_tool('set', *scope, 'gate_steps.%s.test' % step, 'no')
                    self.assertEqual(2, code)
                    self.assertIn('locked on', err)
            _, err, code = self.run_tool('apply', '-', stdin=json.dumps({'gate_steps.%s.dev' % step: False}))
            self.assertEqual(2, code, err)
        self.assertFalse(os.path.exists(self.user) or os.path.exists(self.project), 'a refused change wrote a file')
        _, _, code = self.run_tool('set', 'gate_steps.sast.test', 'yes')
        self.assertEqual(0, code, 'turning a locked step on is allowed')

    def test_a_file_that_holds_them_off_keeps_them_on_and_the_rest_of_the_layer(self):
        with open(self.user, 'w', encoding='utf-8') as handle:
            json.dump({'push': {'prod': False}, 'gate_steps': {'sast': {'test': False}, 'secrets': {'dev': 'no'},
                                                               'compat': {'test': False}}}, handle)
        data = self.values()
        self.assertEqual([], data.get('problems', []))
        values = data['values']
        self.assertEqual((True, True, False, False),
                         (values['gate_steps.sast.test'], values['gate_steps.secrets.dev'], values['gate_steps.compat.test'],
                          values['push.prod']))

    def test_any_other_bad_value_on_a_locked_step_is_still_a_problem(self):
        with open(self.user, 'w', encoding='utf-8') as handle:
            json.dump({'gate_steps': {'sast': {'test': 'maybe'}}}, handle)
        problems = self.values().get('problems', [])
        self.assertEqual(1, len(problems), problems)
        self.assertIn("got 'maybe'", problems[0])

    def test_the_schema_marks_them_locked_for_the_pane(self):
        out, _, _ = self.run_tool('schema')
        locked = sorted({spec['key'].split('.')[1] for spec in json.loads(out) if spec.get('locked')})
        self.assertEqual(sorted(cfg.LOCKED_STEPS), locked)
        self.assertEqual(['sast', 'secrets'], locked)


class InTheProject(Tool):
    def test_the_ticks_are_written_where_the_gate_reads_them(self):
        with open(self.user, 'w', encoding='utf-8') as handle:
            json.dump({'gate_steps': {'compat': {'test': False}}}, handle)
        env = dict(os.environ, PODIUM_CONFIG_USER=self.user, PODIUM_SESSION_DIR=os.path.join(self.home, 'sessions'))
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'sdlc_settings.py'), 'write', '--project', self.repo],
                              capture_output=True, text=True, env=env)
        self.assertEqual(0, done.returncode, done.stderr)
        with open(os.path.join(self.repo, '.claude', 'sdlc-settings.json'), encoding='utf-8') as handle:
            steps = json.load(handle)['settings']['gate_steps']
        self.assertIs(False, steps['compat']['test'])
        self.assertIs(True, steps['compat']['dev'])
        self.assertEqual(sorted(step for step, _, _ in cfg.GATE_STEPS), sorted(steps))


if __name__ == '__main__':
    unittest.main()
