"""The prod branch of the shared gate — the one that had no tests.

This is where rule #33 is enforced. Two checks are OPT-IN: e2e (03/10/2026, GATE_RUN_E2E=1)
and the test deploy check (04/10/2026, GATE_CHECK_TEST_DEPLOY=1). By default the gate runs
neither and WARNS that it did not; once requested, a red result blocks.
The deploy check is the kind that is worthless if it fails OPEN, so the tests here
are mostly about what happens when something is missing or ambiguous:

  · no way to read the deployed SHA -> SKIPPED, and a skip is not a pass;
  · the version endpoint answers with the SPA's HTML instead of a SHA -> failure,
    not "looks fine" (the fallback swallowing /version is a recorded incident);
  · several sites on test reporting DIFFERENT SHAs -> not deployed;
  · e2e requested (GATE_RUN_E2E=1) with no suite at all -> "nothing proves this promotion".

The gate is run from its real path so the measurement lands on it; see the note
in test_gate_core_fixes.py.
The deploy-check classes moved verbatim to test_gate_core_prod_deploy.py (rule #9: 300 lines).
"""
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
os.environ.setdefault('PODIUM_SETTINGS_SOURCE', 'file')  # a developer's own live panel must not change a result (gate-lib-panel.sh)

SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
GATE = os.path.join(SCRIPTS, 'gate-core.sh')
ANSI = re.compile(r'\x1b\[[0-9;]*m')

RULE_16_DOCS = {'SETUP.md': '# Setup\n## Secret and token inventory\n', '.env.example': ''}
# Records the directory it ran in. `pwd -W` gives Git Bash's Windows form (C:/...): its plain `pwd`
# says /c/..., which Python on Windows reads as C:\c\.... Elsewhere -W fails and plain pwd answers.
PWD_STUB = '#!/bin/sh\n{{ pwd -W 2>/dev/null || pwd; }} > "{marker}"\n'


# prod runs the SAME step set as dev and test (29/10/2026): a conf that is not about one of those steps
# makes each of them pass (the last assignment wins), so a test sees only the prod-specific behaviour.
COVERED = ('COVERAGE_CMD="true"\nSAST_CMD="true"\nBACKCOMPAT_CMD="true"\n'
           'ACCEPTED_GAPS="e2e spec check"\nACCEPTED_GAPS_REASON="fixture has no e2e suite"\n')


class ProdGate(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', self.root], check=True)
        subprocess.run(['git', 'config', 'user.email', 't@t'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.name', 't'], cwd=self.root, check=True)
        os.makedirs(os.path.join(self.root, 'scripts'), exist_ok=True)
        self.bin = os.path.join(self.root, '.stubbin')
        os.makedirs(self.bin)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def stub(self, name, body):
        path = os.path.join(self.bin, name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    def write(self, relative, text):
        path = os.path.join(self.root, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)

    def commit(self):
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'base'], cwd=self.root, check=True)
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.root,
                              capture_output=True, text=True).stdout.strip()

    def setup_project(self, conf='', extra=None):
        files = dict(RULE_16_DOCS)
        # Coverage runs at prod too (#29): a project that is not about coverage measures "fine" by default;
        # a conf line below may override it (the last assignment wins).
        files['scripts/merge-gate.conf'] = COVERED + conf
        files.update(extra or {})
        for name, text in files.items():
            self.write(name, text)
        # the CLAUDE.md gates the shared set runs at every target
        self.write('scripts/md-size-gate.sh', '#!/bin/sh\nexit 0\n')
        os.chmod(os.path.join(self.root, 'scripts', 'md-size-gate.sh'), 0o700)
        self.write('scripts/md-rule-gate.py', '')
        return self.commit()

    def run_gate(self, *args, env_extra=None, target='prod'):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ['PATH'], **(env_extra or {}))
        for flag in ('GATE_RUN_E2E', 'GATE_CHECK_TEST_DEPLOY'):
            if not env_extra or flag not in env_extra:
                env.pop(flag, None)
        result = subprocess.run(['bash', GATE, target, *args], cwd=self.root,
                                capture_output=True, text=True, env=env)
        return ANSI.sub('', result.stdout), result.returncode


class ProdRunsCoverage(ProdGate):
    """CLAUDE.md #29: the coverage step runs at every promotion coverage_before_push turns on (prod by default). The prod target used to run only the
    prod-specific steps and ended GATE GREEN with the threshold unmeasured (found 29/10/2026)."""

    def test_it_runs_the_coverage_command(self):
        marker = os.path.join(self.root, 'cov-ran')
        self.setup_project(conf=f'COVERAGE_CMD="touch {marker}; echo web 91.0% lines"\n')
        out, code = self.run_gate()
        self.assertEqual(0, code, out)
        self.assertTrue(os.path.exists(marker), 'the prod gate did not run coverage')
        self.assertIn('web 91.0% lines', out)

    def test_a_red_measurement_closes_the_prod_gate(self):
        self.setup_project(conf='COVERAGE_CMD="exit 1"\n')
        out, code = self.run_gate()
        self.assertEqual(1, code, out)
        self.assertIn('GATE CLOSED', out)

    def test_an_unmeasured_codebase_is_incomplete_never_green(self):
        self.setup_project()
        with open(os.path.join(self.root, 'scripts', 'merge-gate.conf'), 'w') as handle:
            handle.write('')
        subprocess.run(['git', 'commit', '-qam', 'no coverage'], cwd=self.root, check=True)
        out, code = self.run_gate()
        self.assertNotEqual(0, code, out)
        self.assertIn('GATE INCOMPLETE', out)
        self.assertIn('the threshold is NOT measured', out)

    def test_the_listing_names_the_coverage_step(self):
        self.setup_project()
        out, _ = self.run_gate('--list')
        self.assertIn('coverage (>= 80% lines, per codebase)', out)


class ProdRunsTheSharedStepSet(ProdGate):
    """The gate is the same for dev, test and prod (29/10/2026). prod used to run only its own extras and
    ended GATE GREEN with secret scan, SAST, backward compatibility and the CLAUDE.md gates never run."""

    def steps(self, target):
        out, _ = self.run_gate('--list', target=target)
        return [line.strip() for line in out.splitlines() if line.strip().startswith('→')]

    def test_prod_lists_every_step_dev_lists(self):
        self.setup_project()
        dev, prod = self.steps('dev'), self.steps('prod')
        self.assertTrue(dev, 'the dev listing was empty')
        missing = [step for step in dev if step not in prod]
        self.assertEqual([], missing, f'steps dev runs and prod does not: {missing}')

    def test_a_red_sast_closes_the_prod_gate(self):
        self.setup_project(conf='SAST_CMD="exit 1"\n')
        out, code = self.run_gate()
        self.assertEqual(1, code, out)
        self.assertIn('GATE CLOSED', out)

    def test_an_unconfigured_sast_is_incomplete_at_prod_as_at_dev(self):
        self.setup_project()
        self.write('scripts/merge-gate.conf', 'COVERAGE_CMD="true"\nBACKCOMPAT_CMD="true"\n'
                   'ACCEPTED_GAPS="e2e spec check"\nACCEPTED_GAPS_REASON="no suite"\n')
        subprocess.run(['git', 'commit', '-qam', 'no sast'], cwd=self.root, check=True)
        out, code = self.run_gate()
        self.assertNotEqual(0, code, out)
        self.assertIn('GATE INCOMPLETE', out)
        self.assertIn('SAST', out)


class E2eRunsOnRequest(ProdGate):
    """GATE_RUN_E2E=1: the previous behaviour, now opt-in."""

    def run_gate(self, *args, **kw):
        kw.setdefault('env_extra', {'GATE_RUN_E2E': '1'})
        return super().run_gate(*args, **kw)

    def test_with_no_suite_the_promotion_is_unproven(self):
        self.setup_project(conf='TEST_DEPLOY_SHA_CMD="echo x"\n')
        out, code = self.run_gate()
        self.assertIn('nothing proves this promotion', out)
        self.assertNotEqual(0, code)

    def test_a_configured_web_suite_is_run(self):
        marker = os.path.join(self.root, 'e2e-ran.txt')
        sha = self.setup_project(extra={'e2e/smoke.spec.ts': "test('s', () => {})\n"})
        self.write('scripts/merge-gate.conf',     # '/': the gate evals it, and sh eats Windows' '\'
                   COVERED + f'TEST_DEPLOY_SHA_CMD="echo {sha}"\nE2E_WEB_CMD="touch {marker.replace(os.sep, "/")}"\n')
        out, code = self.run_gate()
        self.assertTrue(os.path.exists(marker), f'the e2e command was never run:\n{out}')
        self.assertIn('web e2e', out)

    def test_a_suite_inside_the_web_tier_is_found_and_run_from_there(self):
        # web/e2e used to be invisible: the gate looked for e2e/ or tests/e2e/ at the root only and
        # said "no e2e suite" about a project that had one.
        marker = os.path.join(self.root, 'e2e-cwd.txt')
        self.stub('npx', PWD_STUB.format(marker=marker.replace(os.sep, '/')))
        sha = self.setup_project(extra={'web/package.json': '{"name":"w"}\n',
                                        'web/e2e/smoke.spec.ts': "test('s', () => {})\n"})
        self.write('scripts/merge-gate.conf', COVERED + f'TEST_DEPLOY_SHA_CMD="echo {sha}"\n')
        out, _ = self.run_gate()
        self.assertNotIn('no e2e suite', out)
        self.assertIn('web e2e', out)
        with open(marker, encoding='utf-8') as handle:
            self.assertTrue(handle.read().strip().endswith('/web'), 'the suite must run inside web/')

    def test_a_root_suite_still_runs_from_the_root(self):
        marker = os.path.join(self.root, 'e2e-cwd.txt')
        self.stub('npx', PWD_STUB.format(marker=marker.replace(os.sep, '/')))
        sha = self.setup_project(extra={'web/package.json': '{"name":"w"}\n',
                                        'e2e/smoke.spec.ts': "test('s', () => {})\n"})
        self.write('scripts/merge-gate.conf', COVERED + f'TEST_DEPLOY_SHA_CMD="echo {sha}"\n')
        self.run_gate()
        with open(marker, encoding='utf-8') as handle:
            self.assertEqual(os.path.realpath(self.root), os.path.realpath(handle.read().strip()))

    def test_a_web_directory_without_an_e2e_folder_is_still_no_suite(self):
        self.setup_project(conf='TEST_DEPLOY_SHA_CMD="echo x"\n',
                           extra={'web/package.json': '{"name":"w"}\n'})
        out, _ = self.run_gate()
        self.assertIn('nothing proves this promotion', out)

    def test_a_failing_e2e_suite_closes_the_gate(self):
        sha = self.setup_project(extra={'e2e/smoke.spec.ts': "test('s', () => {})\n"})
        self.write('scripts/merge-gate.conf',
                   COVERED + f'TEST_DEPLOY_SHA_CMD="echo {sha}"\nE2E_WEB_CMD="exit 1"\n')
        out, code = self.run_gate()
        self.assertIn('GATE CLOSED', out)
        self.assertEqual(1, code)


class E2eIsOptionalByDefault(ProdGate):
    def test_a_present_suite_is_not_run_and_the_gate_warns(self):
        marker = os.path.join(self.root, 'e2e-ran.txt')
        sha = self.setup_project(extra={'e2e/smoke.spec.ts': "test('s', () => {})\n"})
        self.write('scripts/merge-gate.conf',     # '/': the gate evals it, and sh eats Windows' '\'
                   COVERED + f'TEST_DEPLOY_SHA_CMD="echo {sha}"\nE2E_WEB_CMD="touch {marker.replace(os.sep, "/")}"\n')
        out, code = self.run_gate()
        self.assertFalse(os.path.exists(marker), f'e2e must not run by default:\n{out}')
        self.assertIn('e2e was NOT run', out)
        self.assertEqual(0, code, out)

    def test_a_project_without_a_suite_is_not_blocked_by_e2e(self):
        sha = self.setup_project()
        self.write('scripts/merge-gate.conf', COVERED + f'TEST_DEPLOY_SHA_CMD="echo {sha}"\n')
        out, code = self.run_gate()
        self.assertIn('e2e was NOT run', out)
        self.assertNotIn('nothing proves this promotion', out)
        self.assertEqual(0, code, out)

    def test_the_warning_never_hides_a_failed_deploy_check(self):
        self.setup_project(conf='TEST_DEPLOY_SHA_CMD="echo deadbeefdeadbeef"\n')
        out, code = self.run_gate(env_extra={'GATE_CHECK_TEST_DEPLOY': '1'})
        self.assertIn('e2e was NOT run', out)
        self.assertIn('GATE CLOSED', out)
        self.assertEqual(1, code)

    def test_the_test_promotion_warns_too(self):
        self.setup_project()
        out, _ = self.run_gate(target='test')
        self.assertIn('e2e was NOT run', out)

    def test_the_dev_promotion_does_not_mention_it(self):
        self.setup_project()
        out, _ = self.run_gate(target='dev')
        self.assertNotIn('e2e was NOT run', out)


if __name__ == '__main__':
    unittest.main()
