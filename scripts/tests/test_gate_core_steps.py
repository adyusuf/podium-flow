"""The gate's steps the user can untick (user decision 02/11/2026): `gate_steps.<id>.<target>` in the project's
.claude/sdlc-settings.json, one per row of GATE_STEPS in gate-lib.sh.

What matters:

  · an unticked step does not run, prints WAIVED and is never counted as passed; the result names it for Gate-Waived;
  · a ticked step, a missing key or another target's tick runs it; only an explicit false waives;
  · a file that does not parse runs every step and says so (fail closed);
  · the parallel Node track honours the ticks too.

Mutation-checked: making gate_step return 0 for an unticked step, or step_on ignore GATE_STEPS_OFF, turns these red.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_gate_core_coverage_only import GateProject  # noqa: E402

SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, SCRIPTS)
import podium_schema  # noqa: E402


class GateSteps(GateProject):
    def setUp(self):
        super().setUp()
        self.sast = os.path.join(self.project, 'sast-ran')
        self.secrets = os.path.join(self.project, 'secrets-ran')
        self.compat = os.path.join(self.project, 'compat-ran')
        # Every command passes, so only what the ticks change decides the verdict.
        self.conf = (self.measured() + f'SAST_CMD="touch {self.sast}"\nSECRET_CMD="touch {self.secrets}"\n'
                     f'BACKCOMPAT_CMD="touch {self.compat}"\n')

    def steps(self, **ticks):
        os.makedirs(os.path.join(self.project, '.claude'), exist_ok=True)
        with open(os.path.join(self.project, '.claude', 'sdlc-settings.json'), 'w', encoding='utf-8') as handle:
            json.dump({'version': 1, 'settings': {'gate_steps': ticks}}, handle)

    def test_an_unticked_step_does_not_run_and_is_waived_never_passed(self):
        self.steps(compat={'dev': False, 'test': True})
        out, _ = self.gate(self.conf)
        self.assertFalse(os.path.exists(self.compat), out)
        self.assertIn('WAIVED: compat (gate_steps.compat.dev = no', out)
        self.assertIn('- WAIVED compat (configuration; the merge commit must carry Gate-Waived: compat)', out)
        self.assertNotIn('✓ backward compatibility', out)
        self.assertTrue(os.path.exists(self.secrets), 'a ticked step still runs')

    def test_a_pull_request_that_turns_off_the_secret_scan_and_sast_changes_nothing(self):
        # The file is the project's own, so a pull request can commit it; the two locked steps run whatever it says.
        self.steps(secrets={'dev': False}, sast={'dev': False}, compat={'dev': False})
        out, _ = self.gate(self.conf)
        self.assertTrue(os.path.exists(self.secrets) and os.path.exists(self.sast), out)
        for step in ('secrets', 'sast'):
            self.assertIn('gate_steps.%s.dev = no in .claude/sdlc-settings.json was IGNORED: %s is locked' % (step, step), out)
            self.assertNotIn('WAIVED: %s' % step, out)
        self.assertFalse(os.path.exists(self.compat), 'a step that is not locked is still waived')
        self.assertIn('WAIVED: compat', out)

    def test_the_tick_of_another_target_does_not_waive_this_one(self):
        self.steps(compat={'dev': False})
        out, _ = self.gate(self.conf, target='test')
        self.assertTrue(os.path.exists(self.compat), out)
        self.assertNotIn('WAIVED: compat', out)

    def test_only_false_waives_and_a_missing_file_runs_every_step(self):
        for ticks in ({'compat': {'dev': True}}, {'compat': {'dev': 'no'}}, {'compat': {'dev': None}}, {}):
            with self.subTest(ticks=ticks):
                self.steps(**ticks)
                out, _ = self.gate(self.conf)
                self.assertTrue(os.path.exists(self.compat), out)
                os.remove(self.compat)
        os.remove(os.path.join(self.project, '.claude', 'sdlc-settings.json'))
        out, _ = self.gate(self.conf)
        self.assertTrue(os.path.exists(self.compat), out)

    def test_a_key_that_is_no_step_id_waives_nothing_even_where_it_would_glob(self):
        # `*` used to expand over the project's files, so a file named `compat` waived that step (qa 02/11/2026).
        for name in ('compat', 'lint'):
            open(os.path.join(self.project, name), 'w', encoding='utf-8').close()
        self.steps(**{'*': {'dev': False}, 'com pat': {'dev': False}})
        out, _ = self.gate(self.conf)
        self.assertTrue(os.path.exists(self.compat), out)
        self.assertNotIn('WAIVED', out)

    def test_a_file_that_does_not_parse_runs_every_step_and_says_so(self):
        os.makedirs(os.path.join(self.project, '.claude'), exist_ok=True)
        with open(os.path.join(self.project, '.claude', 'sdlc-settings.json'), 'w', encoding='utf-8') as handle:
            handle.write('{ broken')
        out, _ = self.gate(self.conf)
        self.assertTrue(os.path.exists(self.compat), out)
        self.assertIn('every gate step runs (fail closed)', out)

    def test_waiving_the_steps_that_would_be_skipped_ends_green_and_names_them(self):
        # In a bare project the md-size gate and the e2e spec check are SKIPPED (INCOMPLETE); unticked, they are waived.
        out, code = self.gate(self.conf)
        self.assertIn('GATE INCOMPLETE', out)
        self.steps(md={'dev': False}, e2e_specs={'dev': False})
        out, code = self.gate(self.conf)
        self.assertEqual(0, code, out)
        self.assertIn('GATE GREEN (with 0 accepted gap(s), 2 step(s) waived by configuration: md e2e_specs)', out)

    def test_a_listing_shows_the_waived_step_and_does_not_list_its_command(self):
        self.steps(compat={'dev': False})
        out, _ = self.gate(self.conf, '--list')
        self.assertIn('WAIVED: compat', out)
        self.assertNotIn(f'touch {self.compat}', out)

    def test_every_step_prints_its_own_heading_from_the_list(self):
        out, _ = self.gate(self.conf)
        for _, _, heading in podium_schema.GATE_STEPS:
            self.assertIn('▶ ' + heading, out)


class EveryStep(GateProject):
    """Each row of GATE_STEPS, unticked alone, stops exactly its own work; ticked, all of it runs. Stub `npm`, `npx` and
    `dotnet` on PATH log what they were asked, so a .NET and a Node tier exercise every step without the real tools."""

    # What each step leaves behind when it runs: a line in the stub log, or a line in the gate's output.
    EVIDENCE = {
        'lint': ('log', 'npm --prefix web run lint'), 'typecheck': ('log', 'npx --prefix web tsc'),
        'build': ('log', 'dotnet build'), 'unit': ('log', 'dotnet test'), 'secrets': ('log', 'secrets'),
        'cve': ('log', 'dotnet list'), 'sast': ('log', 'sast'), 'compat': ('log', 'compat'), 'md': ('log', 'md-size'),
        'documents': ('out', '✓ SETUP.md'), 'e2e_specs': ('out', 'e2e specs: nothing missing'),
    }
    # The rest of a step's work: the other tier, which must stop with it.
    ALSO = {'lint': 'dotnet format', 'build': 'npm --prefix web run build', 'unit': 'npm --prefix web test',
            'cve': 'npm --prefix web audit'}

    def setUp(self):
        super().setUp()
        self.log = os.path.join(self.project, 'ran.log')
        stub = os.path.join(self.project, 'bin')
        os.makedirs(stub)
        for tool, extra in (('npm', ''), ('npx', ''), ('dotnet', 'echo "Project x has no vulnerable packages"\n')):
            with open(os.path.join(stub, tool), 'w', encoding='utf-8') as handle:
                handle.write('#!/bin/sh\necho "%s $*" >> "%s"\n%sexit 0\n' % (tool, self.log, extra))
            os.chmod(os.path.join(stub, tool), 0o755)
        for path, text in (('api/x.csproj', '<Project/>'), ('web/package.json', '{"scripts": {"lint": "x", "build": "x", "test": "x"}}'),
                           ('web/tsconfig.json', '{}'), ('web/node_modules/.keep', ''), ('e2e/.keep', ''), ('SETUP.md', '# Inventory'),
                           ('.env.example', ''), ('scripts/md-size-gate.sh', 'echo md-size >> "%s"\n' % self.log)):
            os.makedirs(os.path.dirname(os.path.join(self.project, path)), exist_ok=True)
            with open(os.path.join(self.project, path), 'w', encoding='utf-8') as handle:
                handle.write(text)
        os.chmod(os.path.join(self.project, 'scripts', 'md-size-gate.sh'), 0o755)
        self.env = dict(os.environ, PATH=stub + os.pathsep + os.environ['PATH'])
        self.conf = (self.measured() + ''.join('%s="echo %s >> %s"\n' % (name, word, self.log)
                     for name, word in (('SECRET_CMD', 'secrets'), ('SAST_CMD', 'sast'), ('BACKCOMPAT_CMD', 'compat'))))

    def run_gate(self, unticked=None):
        os.makedirs(os.path.join(self.project, '.claude'), exist_ok=True)
        with open(os.path.join(self.project, '.claude', 'sdlc-settings.json'), 'w', encoding='utf-8') as handle:
            json.dump({'settings': {'gate_steps': {unticked: {'dev': False}} if unticked else {}}}, handle)
        with open(os.path.join(self.project, 'scripts', 'merge-gate.conf'), 'w', encoding='utf-8') as handle:
            handle.write(self.conf)
        if os.path.exists(self.log):
            os.remove(self.log)
        done = subprocess.run(['bash', 'scripts/gate-core.sh', 'dev'], cwd=self.project, capture_output=True, text=True, env=self.env)
        log = ''
        if os.path.exists(self.log):
            with open(self.log, encoding='utf-8') as handle:
                log = handle.read()
        return log, re.sub(r'\x1b\[[0-9;]*m', '', done.stdout + done.stderr)

    def ran(self, step, log, out):
        where, text = self.EVIDENCE[step]
        return text in (log if where == 'log' else out)

    def test_the_table_covers_every_step_of_the_list(self):
        self.assertEqual(sorted(step for step, _, _ in podium_schema.GATE_STEPS), sorted(self.EVIDENCE))

    def test_ticked_every_step_runs(self):
        log, out = self.run_gate()
        for step in self.EVIDENCE:
            self.assertTrue(self.ran(step, log, out), '%s did not run\n%s\n%s' % (step, log, out))
        for text in self.ALSO.values():
            self.assertIn(text, log)

    def test_an_unticked_step_stops_its_own_work_and_nothing_else(self):
        for step in self.EVIDENCE:
            with self.subTest(step=step):
                log, out = self.run_gate(step)
                if step in podium_schema.LOCKED_STEPS:
                    self.assertTrue(self.ran(step, log, out), 'locked %s did not run\n%s' % (step, out))
                    self.assertIn('was IGNORED: %s is locked' % step, out)
                    continue
                self.assertFalse(self.ran(step, log, out), '%s ran while unticked\n%s' % (step, out))
                if step in self.ALSO:
                    self.assertNotIn(self.ALSO[step], log)
                self.assertIn('WAIVED: %s (gate_steps.%s.dev = no' % (step, step), out)
                others = [one for one in self.EVIDENCE if one != step and not self.ran(one, log, out)]
                self.assertEqual([], others, 'unticking %s stopped other steps' % step)


class NodeTrack(GateProject):
    """GATE_PARALLEL_NODE runs the Node steps in node_track, not under their headings: it must honour the ticks too."""

    def test_the_parallel_track_skips_each_unticked_step(self):
        steps = ['lint', 'typecheck', 'build', 'unit', 'cve']
        for off in steps:
            with self.subTest(off=off):
                script = ('TARGET=dev; LIST_ONLY=0; ROOT="$1"; set -uo pipefail; cd "$1"; . scripts/gate-lib.sh; . scripts/gate-lib-node.sh\n'
                          'node_lint() { echo RAN-lint; }; node_typecheck() { echo RAN-typecheck; }; node_build() { echo RAN-build; }\n'
                          'node_test() { echo RAN-unit; }; node_audit() { echo RAN-cve; }\n'
                          'GATE_STEPS_READ=1; GATE_STEPS_OFF="$2"; node_track\n')
                done = subprocess.run(['bash', '-c', script, 'gate', self.project, off], capture_output=True, text=True)
                ran = [line for line in done.stdout.splitlines() if line.startswith('RAN-')]
                self.assertEqual(['RAN-' + step for step in steps if step != off], ran, done.stdout + done.stderr)


class TheOneList(unittest.TestCase):
    """The pane reads the steps from gate-lib.sh: the same ids the gate checks, none written twice (rule #2)."""

    def test_the_schema_reads_every_step_of_the_gate(self):
        with open(os.path.join(SCRIPTS, 'gate-core.sh'), encoding='utf-8') as handle:
            core = handle.read()
        ids = [step for step, _, _ in podium_schema.GATE_STEPS]
        self.assertGreaterEqual(len(ids), 10)
        self.assertEqual(sorted(ids), sorted(set(ids)))
        for step in ids:
            self.assertIn('gate_step %s;' % step, core, f'GATE_STEPS lists {step}, which gate-core.sh never asks about')
        called = re.findall(r'gate_step ([a-z0-9_]+);', core)
        self.assertEqual(sorted(called), sorted(ids), 'gate-core.sh asks about a step GATE_STEPS does not list')

    def test_an_unreadable_or_malformed_block_gives_no_steps(self):
        self.assertEqual([], podium_schema.gate_steps('/nonexistent/gate-lib.sh'))
        with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False, encoding='utf-8') as handle:
            handle.write("GATE_STEPS='lint|lint|formatter\nBad Id|x|y\nonly|two\nsast|SAST|SAST|locked\nodd|o|O|maybe'\n")
        self.addCleanup(os.remove, handle.name)
        self.assertEqual([('lint', 'lint', 'formatter'), ('sast', 'SAST', 'SAST')], podium_schema.gate_steps(handle.name))
        self.assertEqual(['sast'], podium_schema.locked_steps(handle.name))
        self.assertEqual([], podium_schema.locked_steps('/nonexistent/gate-lib.sh'))

    def test_the_secret_scan_and_sast_are_the_locked_steps(self):
        self.assertEqual(('secrets', 'sast'), podium_schema.LOCKED_STEPS)


if __name__ == '__main__':
    unittest.main()
