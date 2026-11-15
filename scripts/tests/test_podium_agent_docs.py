"""The Agents box's sources outside the code: the D and E mode documents pin MODE_ROLES (F-033), and an agent file's
front matter is read whether its `description:` is one line or a folded/literal block (F-034).

Split from test_podium_config.py, which is past 300 lines; the B and C documents are pinned there.
"""
import importlib.util
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.dirname(SCRIPTS)
_spec = importlib.util.spec_from_file_location('podium_schema', os.path.join(SCRIPTS, 'podium_schema.py'))
schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schema)


def mode_document(name):
    with open(os.path.join(ROOT, 'modes', name), encoding='utf-8') as handle:
        return handle.read()


class ModeDocumentsDAndE(unittest.TestCase):
    """What modes/D-wide-team.md and modes/E-fanout.md say about roles is what MODE_ROLES runs."""

    def test_d_names_exactly_its_fourteen_roles_in_the_agent_set(self):
        text = mode_document('D-wide-team.md')
        self.assertIn('# Mode D — Wide team (%d roles)' % len(schema.MODE_ROLES['D']), text.splitlines()[0])
        section = text.split('## The agent set', 1)[1].split('\n## ', 1)[0]
        self.assertEqual(set(re.findall(r'`([a-z0-9-]+)`', section)), set(schema.MODE_ROLES['D']))
        self.assertEqual(14, len(schema.MODE_ROLES['D']))

    def test_d_is_c_plus_the_five_it_adds(self):
        section = mode_document('D-wide-team.md').split('**The five D adds:**', 1)[1].split('\n\n', 1)[0]
        added = set(re.findall(r'`([a-z0-9-]+)`', section))
        self.assertEqual(added, set(schema.MODE_ROLES['D']) - set(schema.MODE_ROLES['C']))
        self.assertEqual(5, len(added))

    def test_e_is_d_with_workflow_on_top(self):
        text = mode_document('E-fanout.md')
        self.assertIn("On top of D's agent set (%d roles)" % len(schema.MODE_ROLES['D']), text)
        self.assertIn("only this mode's %d role agents" % len(schema.MODE_ROLES['E']), text)
        self.assertEqual(schema.MODE_ROLES['E'], schema.MODE_ROLES['D'])


class FrontMatter(unittest.TestCase):
    """front_matter reads a one-line value, a folded `>` block (lines joined by spaces) and a literal `|` block."""

    def setUp(self):
        self.agents = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.agents, True)
        patcher = mock.patch.object(schema, 'AGENTS_DIR', self.agents)
        patcher.start()
        self.addCleanup(patcher.stop)

    def agent(self, role, front):
        with open(os.path.join(self.agents, role + '.md'), 'w', encoding='utf-8') as handle:
            handle.write('---\nname: %s\n%s---\n\n# Body\ndescription: not this one\n' % (role, front))

    def test_a_one_line_value_is_read_as_it_was(self):
        self.agent('one', 'description: Reads code.\nmodel: sonnet\n')
        self.assertEqual('Reads code.', schema.front_matter('one', 'description', ''))
        self.assertEqual('sonnet', schema.defined_model('one'))

    def test_a_folded_value_joins_its_indented_lines_with_spaces(self):
        self.agent('folded', 'description: >\n  Investigates how code works.\n  Returns short.\n\nmodel: haiku\n')
        self.assertEqual('Investigates how code works. Returns short.', schema.front_matter('folded', 'description', ''))
        self.assertEqual('haiku', schema.defined_model('folded'))

    def test_a_folded_value_with_a_chomping_mark_and_the_last_field_before_the_fence(self):
        self.agent('strip', 'model: opus\ndescription: >-\n    First line\n    second line\n')
        self.assertEqual('First line second line', schema.front_matter('strip', 'description', ''))

    def test_a_literal_value_keeps_its_lines(self):
        self.agent('literal', 'description: |\n  Line one.\n  Line two.\nmodel: sonnet\n')
        self.assertEqual('Line one.\nLine two.', schema.front_matter('literal', 'description', ''))

    def test_an_empty_block_and_a_missing_file_or_field(self):
        self.agent('empty', 'description: >\nmodel: sonnet\n')
        self.assertEqual('', schema.front_matter('empty', 'description', 'missing'))
        self.assertEqual('missing', schema.front_matter('empty', 'tools', 'missing'))
        self.assertEqual('missing', schema.front_matter('no-such-role', 'description', 'missing'))


if __name__ == '__main__':
    unittest.main()
