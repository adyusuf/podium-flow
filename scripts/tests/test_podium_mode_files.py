"""One source for the mode (F-026, 14/11/2026): the project's .claude/mode and .claude/mode-model are the project layer's
`mode` and `mode_model`, so `get`, `show`, `agents` and the session-start block agree with the mode in force.

The order, highest first: the session's layer > the project's .claude/podium.json > its .claude/mode and
.claude/mode-model > the user's file > the shipped defaults. Every test goes through the command line.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_podium_config as base  # noqa: E402


class ModeFiles(base.Tool):
    def write(self, name, text):
        os.makedirs(os.path.join(self.repo, '.claude'), exist_ok=True)
        with open(os.path.join(self.repo, '.claude', name), 'w', encoding='utf-8') as handle:
            handle.write(text)

    def pair(self, key, *scope):
        out, err, code = self.run_tool('show', '--json', *scope)
        self.assertEqual(0, code, err)
        data = json.loads(out)
        return data['values'][key], data['sources'][key]

    def test_the_precedence_chain_end_to_end(self):
        self.assertEqual(('C', 'default'), self.pair('mode'))
        self.run_tool('set', 'mode', 'D')
        self.assertEqual(('D', 'user'), self.pair('mode'))
        self.write('mode', 'b\n')                                       # any case
        self.assertEqual(('B', 'project'), self.pair('mode'))           # the project's file beats the user's
        self.assertEqual(('B\n', '', 0), self.run_tool('get', 'mode'))
        self.run_tool('set', 'mode', 'A', '--project')
        self.assertEqual(('A', 'project'), self.pair('mode'))           # the project's podium.json beats its mode file
        self.run_tool('unset', 'mode', '--project')
        self.assertEqual(('B', 'project'), self.pair('mode'))
        self.run_tool('set', '--session', 's1', 'mode', 'E')
        self.assertEqual(('E', 'session'), self.pair('mode', '--session', 's1'))   # the session beats them all
        self.assertEqual(('B', 'project'), self.pair('mode'))           # and stays in its session
        self.assertEqual(('D', 'user'), self.pair('mode', '--user'))    # --user leaves the project's files out

    def test_the_first_non_empty_line_counts(self):
        self.write('mode', '\n  \n d \nC\n')
        self.assertEqual(('D', 'project'), self.pair('mode'))

    def test_a_mode_file_that_is_not_one_letter_is_a_problem_and_ignored(self):
        self.run_tool('set', 'push.prod', 'no', '--project')
        for text in ('Z\n', 'C sonnet\n', '', '\n\n'):
            self.write('mode', text)
            out, err, code = self.run_tool('get', 'mode')
            self.assertEqual((0, 'C\n'), (code, out), text)
            self.assertIn(os.path.join('.claude', 'mode'), err, text)
            self.assertIn('this file is ignored', err, text)
            data = json.loads(self.run_tool('show', '--json')[0])
            self.assertTrue(any('this file is ignored' in line for line in data['problems']), text)
            self.assertEqual((False, 'project'), (data['values']['push.prod'], data['sources']['push.prod']))   # the rest counts

    def test_mode_model_is_read_the_same_way(self):
        self.write('mode-model', 'Haiku\n')
        self.assertEqual(('haiku', 'project'), self.pair('mode_model'))
        self.run_tool('set', 'mode_model', 'fable', '--project')
        self.assertEqual(('fable', 'project'), self.pair('mode_model'))
        self.run_tool('unset', 'mode_model', '--project')
        for text in ('opus\n', 'gpt\n'):                              # not one of keep/sonnet/haiku/fable
            self.write('mode-model', text)
            out, err, code = self.run_tool('get', 'mode_model')
            self.assertEqual((0, 'sonnet\n'), (code, out), text)
            self.assertIn(os.path.join('.claude', 'mode-model'), err, text)

    def test_a_bad_mode_model_leaves_the_good_mode_letter_in_force(self):
        self.write('mode', 'B\n')
        self.write('mode-model', 'gpt\n')
        self.assertEqual(('B', 'project'), self.pair('mode'))
        self.assertEqual(('sonnet', 'default'), self.pair('mode_model'))

    def test_agents_and_the_session_start_block_follow_the_mode_files(self):
        self.write('mode', 'B\n')
        self.write('mode-model', 'keep\n')
        rows = json.loads(self.run_tool('agents', '--json')[0])
        self.assertEqual(sorted(base.cfg.B_ROLES), sorted(row['role'] for row in rows))
        self.assertIn('mode B, model for the Opus agents: keep', self.run_tool('context')[0])

    def test_the_working_mode_skills_session_choice_beats_the_project_files(self):
        # /podium:working-mode <letter> <model> --once writes the session layer (skills/working-mode §4).
        self.write('mode', 'B\n')
        self.write('mode-model', 'haiku\n')
        for key, value in (('mode', 'D'), ('mode_model', 'keep')):
            self.assertEqual(0, self.run_tool('set', '--session', 's1', key, value)[2])
        rows = {row['role']: row for row in json.loads(self.run_tool('agents', '--json', '--session', 's1')[0])}
        self.assertEqual(14, len(rows))
        self.assertEqual('opus', rows['qa']['runs_on'])                # keep = the defined model
        self.assertFalse(os.path.exists(self.user))
        with open(os.path.join(self.repo, '.claude', 'mode'), encoding='utf-8') as handle:
            self.assertEqual('B\n', handle.read())                      # the project file is never written


if __name__ == '__main__':
    unittest.main()
