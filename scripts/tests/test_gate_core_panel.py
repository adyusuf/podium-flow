"""Where the gate reads the panel's values (user decision 06/11/2026, global #34; gate-lib-panel.sh).

What matters:

  · with the podium plugin installed AND enabled, the LIVE panel (`sdlc_settings.py show`) wins over the project's
    committed .claude/sdlc-settings.json; this session's id is passed so the session's own layer counts;
  · a disabled plugin, a missing tool or a live panel that cannot be read falls back to the file (the last with a warning);
  · gates_before_push.<t> = no turns the gate off by itself: only coverage runs, the result names the waiver and the
    exit code is 10, never 0, so a caller cannot read it as a pass (qa #1); `--list` shows the same (qa #5);
  · in CI the committed file is read even where the plugin is enabled, and gates_before_push does not empty the CI gate
    (qa #2: self-hosted runners run as the user);
  · e2e_before_deploy.prod = yes runs the suite against the test environment; e2e_before_deploy.test = yes runs it on
    DEV (E2E_DEV_*_CMD), never against the test environment (qa #3); asked with no suite or no such environment is a
    warning, not a failure (§8a, qa #4); GATE_RUN_E2E=1 stays prod-only (qa #6).

Mutation-checked: dropping the live branch of panel_resolve, or the `= "yes"` test in gate_e2e_suite, turns these red.
"""
import json
import os
import shutil
import tempfile
import unittest
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_gate_core_coverage_only import GateProject, ANSI  # noqa: E402
import subprocess  # noqa: E402


class PanelSource(GateProject):
    def setUp(self):
        super().setUp()
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.install = os.path.join(self.home, 'plugin')
        os.makedirs(os.path.join(self.install, 'scripts'))
        self.argv_log = os.path.join(self.home, 'argv')
        self.e2e = os.path.join(self.project, 'e2e-ran')

    def file_settings(self, settings):
        os.makedirs(os.path.join(self.project, '.claude'), exist_ok=True)
        with open(os.path.join(self.project, '.claude', 'sdlc-settings.json'), 'w', encoding='utf-8') as handle:
            json.dump({'version': 1, 'settings': settings}, handle)

    def plugin(self, settings=None, enabled=True, tool=True, broken=False):
        with open(os.path.join(self.home, 'settings.json'), 'w', encoding='utf-8') as handle:
            json.dump({'enabledPlugins': {'podium@podium-marketplace': enabled}}, handle)
        os.makedirs(os.path.join(self.home, 'plugins'), exist_ok=True)
        with open(os.path.join(self.home, 'plugins', 'installed_plugins.json'), 'w', encoding='utf-8') as handle:
            json.dump({'plugins': {'podium@podium-marketplace': [{'installPath': self.install}]}}, handle)
        if tool:
            payload = 'not json' if broken else json.dumps({'version': 1, 'settings': settings or {}})
            with open(os.path.join(self.install, 'scripts', 'sdlc_settings.py'), 'w', encoding='utf-8') as handle:
                handle.write('import sys\nopen(%r, "w").write(" ".join(sys.argv[1:]))\nprint(%r)\n' % (self.argv_log, payload))

    def run_gate(self, target='dev', conf='', session=None, source=None, extra=None, args=()):
        with open(os.path.join(self.project, 'scripts', 'merge-gate.conf'), 'w', encoding='utf-8') as handle:
            handle.write(self.measured(0) + conf)
        env = {k: v for k, v in os.environ.items()
               if k not in ('PODIUM_SETTINGS_SOURCE', 'CLAUDE_CODE_SESSION_ID', 'CI', 'GITHUB_ACTIONS', 'GATE_RUN_E2E')}
        env['CLAUDE_CONFIG_DIR'] = self.home
        if session:
            env['CLAUDE_CODE_SESSION_ID'] = session
        if source:
            env['PODIUM_SETTINGS_SOURCE'] = source
        env.update(extra or {})
        done = subprocess.run(['bash', 'scripts/gate-core.sh', target, *args], cwd=self.project, env=env,
                              capture_output=True, text=True)
        return ANSI.sub('', done.stdout + done.stderr), done.returncode

    def test_an_enabled_plugin_s_live_panel_wins_over_the_committed_file(self):
        self.file_settings({'gates_before_push': {'dev': True}})
        self.plugin({'gates_before_push': {'dev': False}})
        out, code = self.run_gate()
        self.assertEqual(10, code, out)
        self.assertIn('settings: the podium panel (live', out)
        self.assertIn('gate off: gates_before_push.dev = no in the podium panel (live)', out)
        self.assertIn('WAIVED the gate (gates_before_push.dev = no', out)
        self.assertIn('COVERAGE GREEN', out)
        self.assertNotIn('GATE GREEN', out)

    def test_this_session_s_layer_is_asked_for(self):
        self.plugin({})
        self.run_gate(session='abc123')
        with open(self.argv_log, encoding='utf-8') as handle:
            self.assertEqual('show --session abc123', handle.read())

    def test_a_disabled_plugin_reads_the_file(self):
        self.file_settings({'gates_before_push': {'dev': False}})
        self.plugin({'gates_before_push': {'dev': True}}, enabled=False)
        out, _ = self.run_gate()
        self.assertNotIn('podium panel (live', out)
        self.assertIn('gate off: gates_before_push.dev = no in .claude/sdlc-settings.json', out)

    def test_an_enabled_plugin_without_its_tool_reads_the_file(self):
        self.file_settings({'gates_before_push': {'dev': False}})
        self.plugin(tool=False)
        out, _ = self.run_gate()
        self.assertIn('gate off: gates_before_push.dev = no in .claude/sdlc-settings.json', out)

    def test_a_live_panel_that_cannot_be_read_falls_back_to_the_file_and_says_so(self):
        self.file_settings({'gates_before_push': {'dev': False}})
        self.plugin(broken=True)
        out, _ = self.run_gate()
        self.assertIn('its panel could not be read - using .claude/sdlc-settings.json', out)
        self.assertIn('gate off: gates_before_push.dev = no in .claude/sdlc-settings.json', out)

    def test_the_tests_switch_forces_the_file(self):
        self.file_settings({'gates_before_push': {'dev': True}})
        self.plugin({'gates_before_push': {'dev': False}})
        out, _ = self.run_gate(source='file')
        self.assertNotIn('gate off', out)
        self.assertNotIn('podium panel (live', out)

    def test_no_file_and_no_plugin_runs_the_gate(self):
        out, _ = self.run_gate()
        self.assertNotIn('gate off', out)
        self.assertIn('secret scan', out)

    def test_e2e_runs_on_prod_when_the_panel_says_yes(self):
        os.makedirs(os.path.join(self.project, 'e2e'))
        self.plugin({'e2e_before_deploy': {'prod': True}})
        out, _ = self.run_gate('prod', conf=f'E2E_WEB_CMD="touch {self.e2e}"\n')
        self.assertTrue(os.path.exists(self.e2e), out)
        self.assertIn('requested: e2e_before_deploy.prod = yes in the podium panel (live)', out)

    def test_e2e_runs_on_dev_for_test_when_the_panel_says_yes_never_against_the_test_environment(self):
        os.makedirs(os.path.join(self.project, 'e2e'))
        against_test = os.path.join(self.project, 'ran-against-test')
        self.plugin({'e2e_before_deploy': {'test': True}})
        out, _ = self.run_gate('test', conf=f'E2E_WEB_CMD="touch {against_test}"\nE2E_DEV_WEB_CMD="touch {self.e2e}"\n')
        self.assertTrue(os.path.exists(self.e2e), out)
        self.assertFalse(os.path.exists(against_test), out)
        self.assertIn('e2e suite on dev', out)
        self.assertNotIn('e2e was NOT run', out)

    def test_e2e_asked_for_test_without_a_dev_command_says_so_and_does_not_block(self):
        os.makedirs(os.path.join(self.project, 'e2e'))
        self.plugin({'e2e_before_deploy': {'test': True}})
        out, _ = self.run_gate('test', conf=f'E2E_WEB_CMD="touch {self.e2e}"\n')
        self.assertFalse(os.path.exists(self.e2e), out)
        self.assertIn('no such environment: set E2E_DEV_WEB_CMD', out)
        self.assertNotIn('SKIPPED e2e', out)

    def test_e2e_asked_by_the_panel_with_no_suite_is_a_warning_not_a_gap(self):
        self.plugin({'e2e_before_deploy': {'prod': True}})
        out, _ = self.run_gate('prod')
        self.assertIn('no e2e suite in this project', out)
        self.assertNotIn('nothing proves this promotion', out)

    def test_gate_run_e2e_stays_prod_only(self):
        os.makedirs(os.path.join(self.project, 'e2e'))
        out, _ = self.run_gate('test', conf=f'E2E_DEV_WEB_CMD="touch {self.e2e}"\n', extra={'GATE_RUN_E2E': '1'})
        self.assertFalse(os.path.exists(self.e2e), out)

    def test_ci_reads_the_committed_file_even_with_the_plugin_enabled(self):
        self.file_settings({'gates_before_push': {'dev': True}})
        self.plugin({'gates_before_push': {'dev': False}})
        out, code = self.run_gate(extra={'CI': 'true'})
        self.assertNotIn('podium panel (live', out)
        self.assertNotIn('gate off', out)
        self.assertNotEqual(10, code, out)

    def test_ci_does_not_empty_the_gate_when_the_file_turns_it_off(self):
        self.file_settings({'gates_before_push': {'dev': False}})
        out, code = self.run_gate(extra={'GITHUB_ACTIONS': 'true'})
        self.assertIn('is a local setting — CI runs the gate', out)
        self.assertIn('secret scan', out)
        self.assertNotEqual(10, code, out)

    def test_list_shows_that_the_gate_is_off(self):
        self.plugin({'gates_before_push': {'dev': False}})
        out, code = self.run_gate(args=('--list',))
        self.assertEqual(0, code, out)
        self.assertIn('gate off: gates_before_push.dev = no', out)
        self.assertIn('LISTING ONLY', out)
        self.assertNotIn('secret scan', out)

    def test_a_plugin_whose_name_only_starts_with_podium_is_not_the_panel(self):
        self.file_settings({'gates_before_push': {'dev': True}})
        self.plugin({'gates_before_push': {'dev': False}})
        with open(os.path.join(self.home, 'settings.json'), 'w', encoding='utf-8') as handle:
            json.dump({'enabledPlugins': {'podium-x@m': True}}, handle)
        out, _ = self.run_gate()
        self.assertNotIn('podium panel (live', out)
        self.assertNotIn('gate off', out)

    def test_a_string_false_does_not_turn_the_gate_off(self):
        self.plugin({'gates_before_push': {'dev': 'false'}})
        out, _ = self.run_gate()
        self.assertNotIn('gate off', out)

    def test_e2e_does_not_run_when_the_panel_says_no_and_the_gate_says_so(self):
        os.makedirs(os.path.join(self.project, 'e2e'))
        self.plugin({'e2e_before_deploy': {'prod': False}})
        out, _ = self.run_gate('prod', conf=f'E2E_WEB_CMD="touch {self.e2e}"\n')
        self.assertFalse(os.path.exists(self.e2e), out)
        self.assertIn('e2e was NOT run', out)

    def test_the_live_copy_is_removed(self):
        self.plugin({})
        tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, tmp, True)
        env_dir = os.environ.get('TMPDIR')
        os.environ['TMPDIR'] = tmp
        try:
            self.run_gate()
        finally:
            if env_dir is None: del os.environ['TMPDIR']
            else: os.environ['TMPDIR'] = env_dir
        self.assertEqual([], [n for n in os.listdir(tmp) if n.startswith('podium-panel.')])


if __name__ == '__main__':
    unittest.main()
