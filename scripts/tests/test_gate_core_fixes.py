"""The JS unit-test step must not hand vitest's flag to jest.

`--run` is a vitest flag. Handing it to a jest project fails with "Unrecognized
option run", so the gate reported a PASSING suite as failing — measured on
It was measured against a mobile suite of 10 tests, which passes on its own.

Each case installs a stub runner at web/node_modules/.bin/<name>, which is where
`npm run` looks first, so `"test": "jest"` really resolves to the stub.

The file grew past that one step: it now pins all five gate-core fixes of
The five: the JS test flag, the coverage refusal, .NET and Node stack
detection, and passing the solution to dotnet as a target. Every one was
mutation-verified; the record is in docs/decision-log.md §25.
Stack detection and the build target moved verbatim to test_gate_core_detection.py (rule #9: 300 lines).

WARNING: keep the `__main__` guard at the BOTTOM of this file. It used to sit in
the middle, above three of the five classes, so `python3 <this file>` ran 2 of
12 tests and printed OK -- the classes below the guard were never even defined.
pytest imports the module, so pytest was unaffected and it went unnoticed.
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
ANSI = re.compile(r'\x1b\[[0-9;]*m')

# The gate is run FROM ITS REAL PATH, never from a copy inside the throwaway
# repository. Two reasons. It behaves identically — gate-core.sh resolves its
# root with `git rev-parse --show-toplevel` and cd's there, so the cwd decides
# what it inspects, not where the file sits (verified: the two runs produce
# byte-identical output). And a coverage tracer attributes execution to the file
# it actually ran: with a copy, scripts/gate-core.sh measures 0% however many
# tests exercise it — which is precisely why shell coverage was unmeasurable
# here and reported as a blocking gap (#29).
GATE = os.path.join(SCRIPTS, 'gate-core.sh')

# Fails when it IS given --run, the way jest does.
JEST_STUB = '#!/bin/sh\nfor a in "$@"; do [ "$a" = "--run" ] && { echo "Unrecognized option run" >&2; exit 1; }; done\necho ran\n'
# Fails when it is NOT given --run, the way a watching vitest would never return.
VITEST_STUB = '#!/bin/sh\nfor a in "$@"; do [ "$a" = "--run" ] && { echo ran; exit 0; }; done\necho "would watch forever" >&2\nexit 1\n'


def project(runner, stub):
    root = tempfile.mkdtemp()
    subprocess.run(['git', 'init', '-q', root], check=True)
    os.makedirs(os.path.join(root, 'scripts'))
    binary = os.path.join(root, 'web', 'node_modules', '.bin')
    os.makedirs(binary)
    path = os.path.join(binary, runner)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(stub)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    if os.name == 'nt':
        # npm runs scripts through cmd.exe there, which finds only the .cmd shim a real install writes.
        with open(path + '.cmd', 'w', encoding='utf-8') as handle:
            handle.write('@"%s" "%%~dp0%s" %%*\r\n' % (shutil.which('bash'), runner))
    with open(os.path.join(root, 'web', 'package.json'), 'w', encoding='utf-8') as handle:
        handle.write('{"name":"w","scripts":{"test":"%s"}}' % runner)
    return root


def unit_test_step(root):
    """Only the lines of the 'unit tests' step."""
    result = subprocess.run(['bash', GATE, 'dev'],
                            cwd=root, capture_output=True, text=True)
    out = ANSI.sub('', result.stdout)
    match = re.search(r'▶ unit tests[^\n]*\n(.*?)\n▶ ', out, re.S)
    return match.group(1) if match else out


class JsTestStep(unittest.TestCase):
    def tearDown(self):
        shutil.rmtree(getattr(self, 'root', ''), ignore_errors=True)

    def test_a_jest_project_is_not_handed_the_vitest_flag(self):
        self.root = project('jest', JEST_STUB)
        step = unit_test_step(self.root)
        self.assertIn('test (web)', step)
        self.assertNotIn('✗ test (web)', step, f"jest was handed --run:\n{step}")

    def test_a_vitest_project_still_gets_the_flag(self):
        self.root = project('vitest', VITEST_STUB)
        step = unit_test_step(self.root)
        self.assertNotIn('✗ test (web)', step, f"vitest did not get --run:\n{step}")



class CoverageCannotBeAccepted(unittest.TestCase):
    """Rule #29 grants no exceptions, so ACCEPTED_GAPS must not waive coverage."""

    def tearDown(self):
        shutil.rmtree(getattr(self, 'root', ''), ignore_errors=True)

    def build(self, accepted, without=()):
        root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', root], check=True)
        os.makedirs(os.path.join(root, 'scripts'))
        with open(os.path.join(root, 'scripts', 'merge-gate.conf'), 'w', encoding='utf-8') as handle:
            handle.write(f'ACCEPTED_GAPS="{accepted}"\nACCEPTED_GAPS_REASON="a written reason"\n')
        self.root = root
        # `without`: the PATH loses the directories holding these tools, so the gate finds them missing.
        path = os.pathsep.join(d for d in os.environ['PATH'].split(os.pathsep)
                               if not any(os.path.exists(os.path.join(d, tool)) for tool in without))
        result = subprocess.run(['bash', GATE, 'test'], cwd=root, capture_output=True, text=True,
                                env=dict(os.environ, PATH=path))
        return ANSI.sub('', result.stdout), result.returncode

    def test_coverage_is_not_accepted_even_when_listed(self):
        out, code = self.build('coverage|SAST')
        self.assertIn('CANNOT be accepted', out)
        self.assertNotIn('ACCEPTED GAP: coverage', out)
        self.assertNotEqual(0, code, 'an unmeasured coverage gate must not exit 0')

    def test_another_gap_is_still_acceptable(self):
        out, _ = self.build('coverage|backward')
        self.assertIn('ACCEPTED GAP: backward-compatibility scan', out)

    # F-012: the secret scan and SAST are locked (rule #19), so they are never an accepted gap either.
    def test_sast_cannot_be_accepted(self):
        out, code = self.build('SAST')
        self.assertIn('CANNOT be accepted — rule #19, the secret scan and SAST are locked): SAST', out)
        self.assertNotIn('ACCEPTED GAP: SAST', out)
        self.assertIn('GATE INCOMPLETE', out)
        self.assertNotEqual(0, code)

    def test_a_missing_gitleaks_cannot_be_accepted_whatever_its_label_says(self):
        # "gitleaks is not installed" names no locked step: the refusal comes from the heading it is under.
        out, code = self.build('gitleaks', without=('gitleaks',))
        self.assertIn('CANNOT be accepted — rule #19, the secret scan and SAST are locked): gitleaks is not installed', out)
        self.assertNotIn('ACCEPTED GAP: gitleaks', out)
        self.assertNotEqual(0, code)

    def test_the_never_acceptable_pattern_is_derived_from_the_locked_rows(self):
        # Outside a locked step's heading the label decides: the locked rows' names come from GATE_STEPS, not a copy.
        self.root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', self.root], check=True)
        script = ('TARGET=dev; LIST_ONLY=0; ROOT="$PWD"; . "$1"; echo "pattern=$NEVER_ACCEPTABLE"\n'
                  'ACCEPTED_GAPS="SAST|secret scan|backward"; ACCEPTED_GAPS_REASON=r\n'
                  'skip "SAST: elsewhere"; skip "secret scan: elsewhere"; skip "backward: elsewhere"\n')
        done = subprocess.run(['bash', '-c', script, 'x', os.path.join(SCRIPTS, 'gate-lib.sh')], cwd=self.root,
                              capture_output=True, text=True)
        out = ANSI.sub('', done.stdout)
        self.assertIn('pattern=coverage|secrets|secret scan|SAST|SAST', out)
        self.assertIn('CANNOT be accepted — rule #19, the secret scan and SAST are locked): SAST: elsewhere', out)
        self.assertIn('CANNOT be accepted — rule #19, the secret scan and SAST are locked): secret scan: elsewhere', out)
        self.assertIn('ACCEPTED GAP: backward: elsewhere', out)

    # F-020: a pattern with an empty branch matches every label - a switch, not a written acceptance.
    def test_an_empty_branch_accepts_nothing(self):
        for accepted in ('backward|', '|backward', 'backward||e2e', '(|backward)'):
            with self.subTest(accepted=accepted):
                out, code = self.build(accepted)
                self.assertIn('has an empty branch, which matches every step — not accepted', out)
                self.assertNotIn('ACCEPTED GAP', out)
                self.assertNotEqual(0, code)


class CoverageWhenItIsActuallyMeasured(unittest.TestCase):
    """The refusal to accept the gap is only half of rule #29. The other half:
    a project that DOES measure must pass the step, and one that measures BELOW
    the threshold must close the gate rather than be waved through."""

    DOCS = {'SETUP.md': '# Setup\n## Secret and token inventory\n', '.env.example': ''}

    def tearDown(self):
        shutil.rmtree(getattr(self, 'root', ''), ignore_errors=True)

    def build(self, coverage_cmd):
        root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', root], check=True)
        os.makedirs(os.path.join(root, 'scripts'))
        files = dict(self.DOCS)
        files['scripts/merge-gate.conf'] = f'COVERAGE_CMD="{coverage_cmd}"\n'
        for name, text in files.items():
            path = os.path.join(root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(text)
        with open(os.path.join(root, 'App.sln'), 'w', encoding='utf-8') as handle:
            handle.write('')
        self.root = root
        result = subprocess.run(['bash', GATE, 'test'],
                                cwd=root, capture_output=True, text=True)
        return ANSI.sub('', result.stdout), result.returncode

    def test_a_measurement_above_the_threshold_passes(self):
        out, _ = self.build('true')
        self.assertIn('\u2713 coverage', out)
        self.assertNotIn('CANNOT be accepted', out)

    def test_a_measurement_below_the_threshold_closes_the_gate(self):
        out, code = self.build('false')
        self.assertIn('\u2717 coverage', out)
        self.assertIn('GATE CLOSED', out)
        self.assertNotEqual(0, code)


class MissingE2eSpecOnlyWarns(unittest.TestCase):
    """A missing e2e spec warns in BOTH directions and blocks neither.

    It used to fail `dev -> test`, which put the whole e2e backlog in front of an
    integration merge. #33 moved the writing to the pre-prod gate, where a spec
    can be verified against a deployed test environment instead of written blind.
    The two things this test holds together: the promotion is not blocked, AND
    the gap is still SAID out loud, so it cannot go silent.
    """

    DOCS = {'SETUP.md': '# Setup\n## Secret and token inventory\n', '.env.example': ''}

    def tearDown(self):
        shutil.rmtree(getattr(self, 'root', ''), ignore_errors=True)

    def build(self, target, suite='e2e/smoke.spec.ts', changed=('src/thing.ts',), extra=None):
        """A repo with an e2e suite, plus a commit that changes behaviour and
        touches no spec — which is exactly the condition the check fires on.
        `suite` is where the suite lives (e2e/ at the root, or web/e2e/ in the web tier) and
        `changed` are the files the second commit touches."""
        root = tempfile.mkdtemp()
        subprocess.run(['git', 'init', '-q', root], check=True)
        subprocess.run(['git', 'config', 'user.email', 't@t'], cwd=root, check=True)
        subprocess.run(['git', 'config', 'user.name', 't'], cwd=root, check=True)
        os.makedirs(os.path.join(root, 'scripts'))
        files = dict(self.DOCS)
        files[suite] = "test('smoke', () => {})\n"
        files.update(extra or {})
        files['scripts/merge-gate.conf'] = 'COVERAGE_CMD="true"\n'
        for name, text in files.items():
            path = os.path.join(root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(text)
        subprocess.run(['git', 'add', '-A'], cwd=root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'base'], cwd=root, check=True)
        # Behaviour changes, no spec touched.
        for name in changed:
            path = os.path.join(root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('export const x = 1\n')
        subprocess.run(['git', 'add', '-A'], cwd=root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'behaviour change, no spec'], cwd=root, check=True)
        self.root = root
        result = subprocess.run(['bash', GATE, target],
                                cwd=root, capture_output=True, text=True)
        return ANSI.sub('', result.stdout), result.returncode

    def test_the_test_promotion_is_not_blocked(self):
        out, _ = self.build('test')
        self.assertNotIn('missing e2e spec blocks', out)
        self.assertNotIn('GATE CLOSED', out, f"dev -> test was blocked by the spec check:\n{out}")

    def test_the_gap_is_still_said_out_loud(self):
        out, _ = self.build('test')
        self.assertIn('no e2e spec was touched', out)
        self.assertIn('reminder only: e2e is optional', out)

    def test_a_suite_in_the_web_tier_is_checked_too(self):
        out, _ = self.build('dev', suite='web/e2e/smoke.spec.ts', changed=('web/lib/thing.ts',),
                            extra={'web/package.json': '{"name":"w"}\n'})
        self.assertIn('no e2e spec was touched', out)
        self.assertNotIn('has no e2e suite', out)

    def test_touching_a_spec_in_the_web_tier_clears_the_warning(self):
        out, _ = self.build('dev', suite='web/e2e/smoke.spec.ts',
                            changed=('web/lib/thing.ts', 'web/e2e/other.spec.ts'),
                            extra={'web/package.json': '{"name":"w"}\n'})
        self.assertNotIn('no e2e spec was touched', out)
        self.assertIn('nothing missing for this change', out)

    def test_changing_only_a_web_tier_e2e_helper_is_not_behaviour(self):
        out, _ = self.build('dev', suite='web/e2e/smoke.spec.ts', changed=('web/e2e/env.ts',),
                            extra={'web/package.json': '{"name":"w"}\n'})
        self.assertNotIn('no e2e spec was touched', out)

    def test_dev_says_it_too_and_does_not_block(self):
        out, _ = self.build('dev')
        self.assertIn('no e2e spec was touched', out)
        self.assertNotIn('GATE CLOSED', out)


if __name__ == '__main__':
    unittest.main()
