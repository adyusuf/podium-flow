"""step-stats.py as a command (F-040, 14/11/2026): `--days`, `--write`, the cuts table, collect and report.

The script reads ~/.claude/projects and writes docs/measurement-log.md beside its own folder, so each test runs a COPY
of it in a temporary folder with HOME pointed at a temporary home holding a small fake transcript: no real transcript is
read and the repository's measurement log is never written. The folders are named with the sanitiser's safe words
(`plugin`, `home`), so its runtime deny-set does not pick them up.
"""
import glob
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
OPUS = 'claude-opus-5-5'


def transcript_line(started, prefix, command=None):
    """One model request at `started` whose first-request prefix is `prefix` tokens, with a Bash call if given."""
    content = [{'type': 'tool_use', 'name': 'Bash', 'input': {'command': command}}] if command else []
    return json.dumps({'timestamp': started, 'message': {'model': OPUS, 'content': content,
                                                         'usage': {'input_tokens': prefix, 'output_tokens': 10}}})


class StepStatsCommand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.root = os.path.join(self.dir, 'plugin')
        os.makedirs(os.path.join(self.root, 'scripts'))
        os.makedirs(os.path.join(self.root, 'docs'))
        for path in [os.path.join(SCRIPTS, 'step-stats.py')] + glob.glob(os.path.join(SCRIPTS, 'step_stats_*.py')):
            shutil.copy(path, os.path.join(self.root, 'scripts'))
        self.script = os.path.join(self.root, 'scripts', 'step-stats.py')
        self.log = os.path.join(self.root, 'docs', 'measurement-log.md')
        self.home = os.path.join(self.dir, 'home')
        self.projects = os.path.join(self.home, '.claude', 'projects', '-x-abc')
        os.makedirs(self.projects)
        self.env = dict(os.environ, HOME=self.home)

    def session(self, name, *lines):
        with open(os.path.join(self.projects, name + '.jsonl'), 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(lines) + '\n')

    def cuts(self, *lines):
        with open(os.path.join(self.root, 'scripts', 'measurement-cuts.tsv'), 'w', encoding='utf-8') as handle:
            handle.write('# ISO timestamp <TAB> label\n' + '\n'.join(lines) + '\n')

    def run_script(self, *args):
        return subprocess.run([sys.executable, self.script, *args], env=self.env, capture_output=True, text=True)

    def module(self):
        spec = importlib.util.spec_from_file_location('step_stats_cli', self.script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.TRANSCRIPTS = os.path.join(self.home, '.claude', 'projects', '**', '*.jsonl')
        return module

    def test_write_reports_the_fake_home_into_the_log(self):
        self.session('s1', transcript_line('2026-10-01T10:00:00Z', 1000, 'npm test -- --run'))
        done = self.run_script('--write')
        self.assertEqual(0, done.returncode, done.stderr)
        with open(self.log, encoding='utf-8') as handle:
            text = handle.read()
        self.assertTrue(text.startswith('# Measurement log — step and agent statistics'), text[:80])
        self.assertIn('Scope: 1 sessions + 0 agent runs, all records', text)
        self.assertIn('- sessions: **1** · model requests: **1**', text)
        self.assertRegex(text, r'\| unit test \| 1 \| ')          # the step that ran is counted from the fake transcript

    def test_days_must_be_a_whole_number(self):
        self.session('s1', transcript_line('2026-10-01T10:00:00Z', 1000))
        for args in (('--days', 'abc'), ('--days', '2.5'), ('--days',)):
            done = self.run_script('--write', *args)
            self.assertEqual(2, done.returncode, args)
            self.assertIn('--days takes a whole number of days', done.stderr, args)
            self.assertNotIn('Traceback', done.stderr, args)
            self.assertFalse(os.path.exists(self.log), args)          # nothing is written
        done = self.run_script('--days', '30')
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(', last 30 days', done.stdout)

    def test_a_bad_cuts_line_is_skipped_with_a_warning_not_a_traceback(self):
        self.session('s1', transcript_line('2026-10-01T10:00:00Z', 1000))
        self.cuts('2026-09-20 09:39\tgood cut', 'not a timestamp\tbad cut', 'no tab at all')
        done = self.run_script()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn('Traceback', done.stderr)
        self.assertIn('measurement-cuts.tsv line 3 is not', done.stderr)
        self.assertIn('measurement-cuts.tsv line 4 is not', done.stderr)
        self.assertIn('| cut 1 | good cut |', done.stdout)
        self.assertNotIn('bad cut', done.stdout)

    def test_compare_cuts_sets_the_median_before_against_after(self):
        for n, prefix in enumerate((1000, 1100, 1200)):
            self.session('before%d' % n, transcript_line('2026-09-0%dT10:00:00+00:00' % (n + 1), prefix))
        for n, prefix in enumerate((800, 900, 1000)):
            self.session('after%d' % n, transcript_line('2026-10-0%dT10:00:00+00:00' % (n + 1), prefix))
        self.session('agent-a1b2c3d4', transcript_line('2026-10-05T10:00:00+00:00', 99999))   # an agent run is not a session
        self.cuts('2026-09-20T00:00:00+00:00\tsmaller prompt')
        table = self.module().compare_cuts()
        self.assertEqual('| cut 1 | smaller prompt | 1,100 · 3 | 900 · 3 | **-200 (-18%)** |', table[-1])

    def test_compare_cuts_without_a_cuts_file_is_no_table(self):
        self.assertEqual([], self.module().compare_cuts())

    def test_collect_keeps_sessions_and_agent_runs_apart_and_honours_the_window(self):
        self.session('s1', transcript_line('2026-10-01T10:00:00Z', 1000))
        self.session('agent-a1b2c3d4', transcript_line('2026-10-01T10:00:00Z', 1000))
        old = os.path.join(self.projects, 'old.jsonl')
        self.session('old', transcript_line('2026-01-01T10:00:00Z', 1000))
        os.utime(old, (0, 0))
        module = self.module()
        sessions, agents = module.collect()
        self.assertEqual(['old.jsonl', 's1.jsonl'], sorted(os.path.basename(path) for path in sessions))
        self.assertEqual(['agent-a1b2c3d4.jsonl'], [os.path.basename(path) for path in agents])
        self.assertEqual(['s1.jsonl'], [os.path.basename(path) for path in module.collect(days=30)[0]])


if __name__ == '__main__':
    unittest.main()
