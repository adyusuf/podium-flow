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


class Ticks(Tool):
    def test_every_step_starts_on_for_every_target(self):
        values = self.values()['values']
        keys = [key for key in values if key.startswith('gate_steps.')]
        self.assertEqual(len(cfg.GATE_STEPS) * len(cfg.TARGETS), len(keys))
        self.assertTrue(all(values[key] is True for key in keys))

    def test_the_saved_choice_comes_back_in_a_new_session_and_the_session_beats_it(self):
        self.run_tool('set', 'gate_steps.sast.test', 'no')
        _, _, code = self.run_tool('set', '--session', 'one', 'gate_steps.lint.test', 'no')
        self.assertEqual(0, code)
        fresh, _, _ = self.run_tool('get', '--session', 'two', 'gate_steps.sast.test')
        self.assertEqual('no', fresh.strip())
        other, _, _ = self.run_tool('get', '--session', 'two', 'gate_steps.lint.test')
        self.assertEqual('yes', other.strip(), 'a session-only tick must not reach another session')
        self.run_tool('set', '--session', 'one', 'gate_steps.sast.test', 'yes')
        now, _, _ = self.run_tool('get', '--session', 'one', 'gate_steps.sast.test')
        self.assertEqual('yes', now.strip())

    def test_an_unknown_step_is_refused(self):
        _, err, code = self.run_tool('set', 'gate_steps.nonsense.dev', 'no')
        self.assertEqual(2, code)
        self.assertIn('unknown setting', err)

    def test_the_context_names_the_unticked_steps_where_the_gate_runs(self):
        self.run_tool('set', 'gate_steps.sast.test', 'no')
        self.run_tool('set', 'gate_steps.compat.dev', 'no')       # the dev gate is off by default: nothing to name
        out, _, _ = self.run_tool('context')
        line = next(text for text in out.splitlines() if text.strip().startswith('test: merge'))
        self.assertIn('gate steps off (waived, named in Gate-Waived): sast', line)   # the id the gate prints
        dev = next(text for text in out.splitlines() if text.strip().startswith('dev: merge'))
        self.assertNotIn('gate steps off', dev)

    def test_the_schema_gives_the_pane_each_steps_name_and_heading(self):
        out, _, _ = self.run_tool('schema')
        specs = [spec for spec in json.loads(out) if spec['key'].startswith('gate_steps.')]
        step, name, heading = cfg.GATE_STEPS[0]
        first = specs[0]
        self.assertEqual(('gate_steps.%s.dev' % step, name, heading, True, 'bool'),
                         (first['key'], first['step'], first['heading'], first['default'], first['type']))


class InTheProject(Tool):
    def test_the_ticks_are_written_where_the_gate_reads_them(self):
        with open(self.user, 'w', encoding='utf-8') as handle:
            json.dump({'gate_steps': {'sast': {'test': False}}}, handle)
        env = dict(os.environ, PODIUM_CONFIG_USER=self.user, PODIUM_SESSION_DIR=os.path.join(self.home, 'sessions'))
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'sdlc_settings.py'), 'write', '--project', self.repo],
                              capture_output=True, text=True, env=env)
        self.assertEqual(0, done.returncode, done.stderr)
        with open(os.path.join(self.repo, '.claude', 'sdlc-settings.json'), encoding='utf-8') as handle:
            steps = json.load(handle)['settings']['gate_steps']
        self.assertIs(False, steps['sast']['test'])
        self.assertIs(True, steps['sast']['dev'])
        self.assertEqual(sorted(step for step, _, _ in cfg.GATE_STEPS), sorted(steps))


if __name__ == '__main__':
    unittest.main()
