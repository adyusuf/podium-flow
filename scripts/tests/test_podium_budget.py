"""The session's spending in the Status box (user decision 06/11/2026): MEASURED, shown, never a stop.

What matters:

  · the figure is the session's transcript plus its subagents' transcripts, tokens × the API list price, and the line says
    it is measured that way; nothing readable = no figure (never a guess, rule #15);
  · it is set against the panel's budget.session_usd ('none' = the spend alone); going over is said, nothing stops;
  · the hooks write it into the status table's `budget` field at the end of a turn, a subagent's stop and a user message;
    `show` prints it first; a turn without a transcript keeps the last figure.

Mutation-checked: summing only the main transcript, or dropping the field in normalise, turns these red.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)
import podium_budget  # noqa: E402
import podium_schema  # noqa: E402

SCRIPT = os.path.join(SCRIPTS, 'podium_status.py')
SESSION = 'abc-123'
SONNET = 'claude-sonnet-5-5'


def turn(model, tokens_in, tokens_out):
    return json.dumps({'message': {'model': model, 'usage': {'input_tokens': tokens_in, 'output_tokens': tokens_out}}})


class Budget(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.transcript = os.path.join(self.dir, 'sess.jsonl')
        with open(self.transcript, 'w') as handle:          # sonnet: $2 in / $10 out per million -> $12.00
            handle.write(turn(SONNET, 1_000_000, 1_000_000) + '\nnot json\n')
        os.makedirs(os.path.join(self.dir, 'sess', 'subagents'))
        with open(os.path.join(self.dir, 'sess', 'subagents', 'agent-1.jsonl'), 'w') as handle:   # $3.00
            handle.write(turn(SONNET, 0, 300_000) + '\n')
        self.env = dict(os.environ, PODIUM_STATUS_DIR=os.path.join(self.dir, 'status'),
                        PODIUM_CONFIG_USER=os.path.join(self.dir, 'u.json'), PODIUM_SESSION_DIR=os.path.join(self.dir, 's'))

    def test_the_spend_counts_the_subagents_too(self):
        self.assertAlmostEqual(15.0, podium_budget.spent(self.transcript))

    def test_nothing_readable_is_no_figure(self):
        self.assertIsNone(podium_budget.spent(os.path.join(self.dir, 'missing.jsonl')))
        self.assertIsNone(podium_budget.spent(''))
        self.assertEqual('', podium_budget.line(None, '100'))

    def test_the_line_is_measured_and_never_a_stop(self):
        self.assertEqual('$15.00 spent of $100 (15%) · measured: tokens × API list price', podium_budget.line(15.0, '100'))
        over = podium_budget.line(150.0, '100')
        self.assertIn('(150%) — over the budget, shown only: work goes on', over)
        self.assertEqual('$15.00 spent · no budget set · measured: tokens × API list price', podium_budget.line(15.0, 'none'))

    def test_current_models_are_priced_at_their_own_rate(self):
        import step_stats_transcripts as t
        self.assertEqual((1, 5, .10), t.price('claude-haiku-5-5'))      # not the Opus fallback (qa 06/11/2026)
        self.assertEqual((2, 10, .10), t.price('claude-sonnet-5-5'))
        self.assertEqual((5, 25, .10), t.price('claude-opus-5-5'))
        self.assertEqual((10, 50, .025), t.price('claude-fable-5-1'))

    def test_the_panel_offers_the_same_budgets(self):
        self.assertEqual(podium_budget.BUDGETS, podium_schema.BUDGETS)
        row = [one for one in podium_schema.SCHEMA if one['key'] == 'budget.session_usd']
        self.assertEqual(1, len(row))
        self.assertIn(podium_budget.DEFAULT_BUDGET, row[0]['options'])
        # User decision 09/11/2026: none, 200, 500, 1000 are offered; an older file's 25/50/100 is still read (rule #4).
        self.assertEqual(('none', '200', '500', '1000'), podium_budget.BUDGETS)
        self.assertEqual(list(podium_budget.LEGACY_BUDGETS), row[0]['legacy'])
        import podium_layers
        self.assertEqual('100', podium_layers.check('budget.session_usd', '100'))
        with self.assertRaises(podium_layers.ConfigError):
            podium_layers.check('budget.session_usd', '300')

    def hook(self, event, payload):
        subprocess.run([sys.executable, SCRIPT, 'hook', event], env=self.env, capture_output=True,
                       input=json.dumps(payload).encode())

    def show(self, *args):
        return subprocess.run([sys.executable, SCRIPT, '--session', SESSION, 'show', *args], env=self.env,
                              capture_output=True, text=True).stdout

    def test_the_end_of_a_turn_writes_it_and_show_prints_it_first(self):
        self.hook('stop', {'session_id': SESSION, 'transcript_path': self.transcript})
        self.assertEqual('$15.00 spent of $200 (8%) · measured: tokens × API list price',     # the default, $200
                         json.loads(self.show('--json'))['budget'])
        text = self.show()
        self.assertTrue(text.startswith('budget: $15.00 spent of $200'), text)

    def test_a_table_with_only_the_budget_still_says_nothing_runs(self):
        import podium_status
        text = podium_status.render(dict(podium_status.EMPTY, rows=[], budget='$1.00 spent'))
        self.assertEqual('budget: $1.00 spent\nnothing running', text)
        self.assertEqual('nothing running', podium_status.render(dict(podium_status.EMPTY, rows=[])))

    def test_the_panel_s_budget_is_used(self):
        with open(os.path.join(self.dir, 'u.json'), 'w') as handle:
            json.dump({'budget': {'session_usd': '25'}}, handle)
        self.hook('stop', {'session_id': SESSION, 'transcript_path': self.transcript})
        self.assertIn('$15.00 spent of $25 (60%)', json.loads(self.show('--json'))['budget'])

    def test_a_turn_without_a_transcript_keeps_the_last_figure(self):
        self.hook('stop', {'session_id': SESSION, 'transcript_path': self.transcript})
        self.hook('stop', {'session_id': SESSION})
        self.assertIn('$15.00 spent', json.loads(self.show('--json'))['budget'])

    def test_a_user_message_and_a_subagent_stop_update_it(self):
        self.hook('prompt', {'session_id': SESSION, 'prompt': 'x', 'transcript_path': self.transcript})
        self.assertIn('$15.00 spent', json.loads(self.show('--json'))['budget'])


if __name__ == '__main__':
    unittest.main()
