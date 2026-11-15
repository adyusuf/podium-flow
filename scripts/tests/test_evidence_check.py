import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), '..')))
import importlib.util
os.environ.setdefault('PODIUM_SETTINGS_SOURCE', 'file')  # a developer's own live panel must not change a result (gate-lib-panel.sh)

CHECKER = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'evidence-check.py'))
spec = importlib.util.spec_from_file_location('evidence_check', CHECKER)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

CLEAN = """report body

## Completeness check — pass 1
- Verification   → `bash scripts/gate-core.sh dev --list` exit 0; read gate-core.sh lines 90-120
- Item mapping   → fail-closed check → scripts/gate-core.sh:112
- Not covered    → prod path not run; deliberately left out: NIST column
→ Result: clean NO
"""

YES_BLOCK = """## Completeness check — pass 2
- Verification   → `grep -n SETUP scripts/gate-core.sh`
- Item mapping   → 
  - inventory heading → scripts/gate-core.sh:118
  - .env.example → scripts/gate-core.sh:116
- Not covered    → nothing
→ Result: YES → BACK TO: developer · add the inventory check · re-run `grep -n inventory scripts/gate-core.sh`
"""


def problems(text):
    return ev.validate(text)[1]


class EvidenceCheck(unittest.TestCase):
    def test_clean_block_is_valid(self):
        self.assertEqual(problems(CLEAN), [])

    def test_yes_block_with_hand_back_is_valid_and_multiline_mapping_parsed(self):
        blocks, errors = ev.validate(YES_BLOCK)
        self.assertEqual(errors, [])
        self.assertEqual(len(blocks[0]['item_mapping']), 2)
        self.assertEqual(blocks[0]['result']['back_to']['who'], 'developer')

    def test_no_block_fails_closed(self):
        self.assertTrue(any('no "## Completeness check' in e for e in problems('just prose')))

    def test_verification_without_evidence_is_rejected(self):
        bad = CLEAN.replace('`bash scripts/gate-core.sh dev --list` exit 0; read gate-core.sh lines 90-120', 'looked fine')
        self.assertTrue(any('verification' in e for e in problems(bad)))

    def test_clean_with_not_verified_is_rejected(self):
        bad = CLEAN.replace('prod path not run', 'prod path not verified')
        self.assertTrue(any('not verified' in e for e in problems(bad)))

    def test_yes_without_hand_back_is_rejected(self):
        bad = YES_BLOCK.replace('developer · add the inventory check · re-run `grep -n inventory scripts/gate-core.sh`', '')
        self.assertTrue(any('BACK TO' in e for e in problems(bad)))

    def test_missing_item_mapping_is_rejected(self):
        bad = CLEAN.replace('- Item mapping   → fail-closed check → scripts/gate-core.sh:112\n', '')
        self.assertTrue(any('item_mapping' in e for e in problems(bad)))

    def test_unknown_result_is_rejected(self):
        bad = CLEAN.replace('clean NO', 'looks good')
        self.assertTrue(any('serious_gap' in e for e in problems(bad)))

    def test_every_block_in_a_report_is_checked(self):
        errors = problems(CLEAN + '\n' + CLEAN.replace('clean NO', 'maybe').replace('pass 1', 'pass 2'))
        self.assertTrue(errors and all(e.startswith('pass 2') for e in errors))


class ThinBlocks(unittest.TestCase):
    """F-025: a block copied from the template, or one whose only evidence is `ls`, passed."""

    VERIFICATION = '`bash scripts/gate-core.sh dev --list` exit 0; read gate-core.sh lines 90-120'

    def cli(self, text):
        done = subprocess.run([sys.executable, CHECKER, '-'], input=text, capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def test_the_template_alternative_as_the_result_is_rejected(self):
        for result in ('clean NO  |  YES → BACK TO: <who> · <what to fix> · <closing evidence>',
                       'serious gap NO | YES', 'NO|YES'):
            code, out = self.cli(CLEAN.replace('clean NO', result))
            self.assertEqual(1, code, result)
            self.assertIn('template alternative', out, result)

    def test_a_verdict_that_merely_mentions_the_alternative_later_is_not_the_template(self):
        self.assertEqual(problems(YES_BLOCK.replace('add the inventory check', 'fix the NO | YES parsing')), [])

    def test_a_single_backticked_word_is_not_evidence(self):
        for verification in ('`ls`', '`ok` and `fine`', '` pytest `'):
            code, out = self.cli(CLEAN.replace(self.VERIFICATION, verification))
            self.assertEqual(1, code, verification)
            self.assertIn('single backticked word', out, verification)

    def test_a_command_a_path_or_a_location_still_counts(self):
        for verification in ('`pytest -q`', '`scripts/gate-core.sh`', '`ls` then read gate-core.sh:12',
                             '`ls` and lines 3-9', '`grep -n x a.py`'):
            self.assertEqual(problems(CLEAN.replace(self.VERIFICATION, verification)), [], verification)

    def test_a_clean_block_passes_through_the_command_line(self):
        code, out = self.cli(CLEAN)
        self.assertEqual(0, code, out)
        self.assertIn('1 evidence block(s) valid', out)


if __name__ == '__main__':
    unittest.main()
