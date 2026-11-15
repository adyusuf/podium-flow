"""Layer 2 of the Status box (user decision 15/11/2026, order confirmed 16/11/2026: state, then agent, then the agent's
tasks): each subagent row is titled `<description> (<model>)` from the harness's meta file, its state comes only from
harness events (a usage limit is "failed: rate limit", never "done"), a resumed agent reopens its own row and carries
its time and tool calls on, and fifteen agents at once keep fifteen rows apart.

Each test runs the scripts as commands with the status folder in a temporary directory, as test_podium_status_agents.py.
"""
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_podium_status_agents as base  # noqa: E402

SESSION = base.SESSION
QA = {'session_id': SESSION, 'agent_type': 'podium:qa', 'agent_id': 'ae234bb11af9b5686'}
QA_NAME = 'podium:qa ae234b'


def answer(model='claude-sonnet-5-5', tool=None, out=10, ident=None):
    """One assistant line of an agent transcript: a tool call `tool` (an id) or plain text, with its output tokens."""
    content = [{'type': 'tool_use', 'id': tool, 'name': 'Read'}] if tool else [{'type': 'text', 'text': 'x'}]
    return {'type': 'assistant', 'message': {'id': ident or tool or 'm-%d' % out, 'model': model, 'content': content,
                                             'usage': {'output_tokens': out}}}


# The line a usage limit leaves, as seen in agent-ada8eb8363b165ea1.jsonl (15/11/2026).
RATE_LIMIT = {'type': 'assistant', 'isApiErrorMessage': True, 'error': 'rate_limit', 'apiError': 'usage_limit_reached',
              'message': {'id': 'err', 'model': '<synthetic>', 'content': [{'type': 'text', 'text': "You've hit your limit"}]}}


class Layer2(unittest.TestCase):
    # The helpers of test_podium_status_agents.py, borrowed rather than inherited so its tests do not run twice.
    setUp, run_tool, run_hook = base.AgentRows.setUp, base.AgentRows.run_tool, base.AgentRows.run_hook
    table, rows, age = base.AgentRows.table, base.AgentRows.rows, base.AgentRows.age

    def session_files(self, description='QA review of ti-batch', model='sonnet', agent=QA):
        """The session transcript path the hooks are given, with the agent's meta file where the harness writes it."""
        session = os.path.join(self.dir, 'proj', SESSION + '.jsonl')
        meta_dir = os.path.join(self.dir, 'proj', SESSION, 'subagents')
        os.makedirs(meta_dir, exist_ok=True)
        with open(os.path.join(meta_dir, 'agent-%s.meta.json' % agent['agent_id']), 'w', encoding='utf-8') as handle:
            json.dump({'agentType': agent['agent_type'], 'description': description, 'model': model, 'finished': False}, handle)
        return dict(agent, transcript_path=session), os.path.join(meta_dir, 'agent-%s.jsonl' % agent['agent_id'])

    def write_transcript(self, path, lines):
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(json.dumps(line) for line in lines) + '\n')

    def test_the_row_is_titled_by_the_meta_description_and_the_measured_model(self):
        payload, transcript = self.session_files()
        self.run_hook('subagent', payload)
        row = self.rows(QA_NAME)[0]
        self.assertEqual(('running', 'QA review of ti-batch (sonnet)'), (row['state'], row['label']))   # the alias asked for
        self.write_transcript(transcript, [answer(tool='t1'), answer(tool='t2')])
        self.run_hook('subagent-stop', dict(payload, agent_transcript_path=transcript))
        row = self.rows(QA_NAME)[0]
        self.assertEqual(('done', '', 'QA review of ti-batch (Sonnet 5.5)'), (row['state'], row['percent'], row['label']))
        self.assertIn('Sonnet 5.5', row['note'])
        self.assertIn('2 tool uses', row['note'])

    def test_no_meta_file_leaves_no_label_and_the_row_still_works(self):
        self.run_hook('subagent', dict(QA, transcript_path=os.path.join(self.dir, 'nowhere', SESSION + '.jsonl')))
        self.run_hook('subagent-stop', QA)
        row = self.rows(QA_NAME)[0]
        self.assertEqual(('done', ''), (row['state'], row['label']))

    def test_a_usage_limit_is_failed_rate_limit_not_done(self):
        payload, transcript = self.session_files()
        self.run_hook('subagent', payload)
        self.write_transcript(transcript, [answer(tool='t1'), RATE_LIMIT])
        self.run_hook('subagent-stop', dict(payload, agent_transcript_path=transcript))
        row = self.rows(QA_NAME)[0]
        self.assertEqual(('failed', 'rate limit', ''), (row['state'], row['blocker'], row['percent']))
        self.assertIn(QA_NAME + ' | task | failed', self.run_tool('show')[0])

    def test_a_limit_the_agent_got_past_after_a_resume_ends_done(self):
        # Only the transcript's LAST answer counts: an earlier limit the agent was resumed past is history, not a failure.
        payload, transcript = self.session_files()
        self.run_hook('subagent', payload)
        self.write_transcript(transcript, [answer(tool='t1'), RATE_LIMIT])
        self.run_hook('subagent-stop', dict(payload, agent_transcript_path=transcript))
        self.run_hook('subagent', payload)
        self.write_transcript(transcript, [answer(tool='t1'), RATE_LIMIT, answer(tool='t2'), answer(ident='last')])
        self.run_hook('subagent-stop', dict(payload, agent_transcript_path=transcript))
        row = self.rows(QA_NAME)[0]
        self.assertEqual(('done', ''), (row['state'], row['blocker']))

    def test_a_resume_reopens_the_same_row_and_its_time_and_tool_calls_carry_on(self):
        payload, transcript = self.session_files()
        self.run_hook('subagent', payload)
        self.age(QA_NAME, 60)
        self.write_transcript(transcript, [answer(tool='t1'), answer(tool='t2')])
        self.run_hook('subagent-stop', dict(payload, agent_transcript_path=transcript))
        self.assertRegex(self.rows(QA_NAME)[0]['note'], r'1m0\ds')      # 60 s and the second the hook took
        self.run_hook('subagent', payload)                          # SendMessage resumes the agent
        rows = self.rows(QA_NAME)
        self.assertEqual(1, len(rows))                              # the same row, not a second one
        self.assertEqual(('running', '1'), (rows[0]['state'], rows[0]['resumed']))
        self.assertIn('resumed ×1', rows[0]['note'])
        self.assertRegex(rows[0]['note'], r'1m0\ds')                 # the earlier run's time is still there
        self.age(QA_NAME, 30)
        self.run_hook('tool', payload)
        self.assertIn('3 tool uses', self.rows(QA_NAME)[0]['note'])     # 2 counted at the first stop, +1
        self.write_transcript(transcript, [answer(tool='t%d' % n) for n in range(1, 6)])
        self.run_hook('subagent-stop', dict(payload, agent_transcript_path=transcript, tool_uses=3, duration_ms=30000))
        row = self.rows(QA_NAME)[0]
        self.assertEqual('done', row['state'])
        self.assertRegex(row['note'], r'1m3\ds')                     # 60 s + 30 s, not the last run alone
        self.assertIn('5 tool uses', row['note'])                   # the transcript holds every run; the payload one
        self.assertIn('resumed ×1', row['note'])

    def test_fifteen_agents_at_once_keep_fifteen_rows_apart(self):
        agents = [dict(QA, agent_type='podium:developer', agent_id='%02dabcdef' % n) for n in range(15)]
        for agent in agents:
            self.run_hook('subagent', agent)
        for n, agent in enumerate(agents):
            for _ in range(n % 3):
                self.run_hook('tool', agent)
        for agent in reversed(agents):
            self.run_hook('subagent-stop', dict(agent, error='boom') if agent['agent_id'].startswith('07') else agent)
        rows = [row for row in self.rows() if row['agent'].startswith('podium:developer')]
        self.assertEqual(15, len(rows))
        self.assertEqual(15, len({row['agent'] for row in rows}))
        states = {row['agent']: row['state'] for row in rows}
        self.assertEqual('failed', states.pop('podium:developer 07abcd'))
        self.assertEqual({'done'}, set(states.values()))
        # Each agent's own tool calls, none of another's (the time beside them is whatever the run took).
        by_agent = {row['agent']: row['note'] for row in rows}
        for n, agent in enumerate(agents):
            note = by_agent['podium:developer ' + agent['agent_id'][:6]]
            if n % 3:
                self.assertIn('%d tool use%s' % (n % 3, '' if n % 3 == 1 else 's'), note)
            else:
                self.assertNotIn('tool use', note)

    def test_hand_written_steps_and_an_older_file_stay_as_they_were(self):
        # Backward compatibility (#4): `step` writes a step as before, and a file written before label/spent/resumed reads
        # with them empty; resuming such a row counts from what it has.
        self.assertEqual(0, self.run_tool('step', '1. read', 'running', '40')[2])
        path = os.path.join(self.dir, SESSION + '.json')
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        data['rows'].append({'item': 'task', 'state': 'done', 'figure': '100%', 'waiting': '', 'percent': '100', 'blocker': '',
                             'agent': QA_NAME, 'note': '', 'since': str(int(time.time()) - 10), 'tools': '4', 'model': ''})
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle)
        rows = self.rows()
        self.assertEqual(('1. read', 'running', '40', ''), (rows[0]['item'], rows[0]['state'], rows[0]['percent'], rows[0]['label']))
        self.run_hook('subagent', QA)
        row = self.rows(QA_NAME)[0]
        self.assertEqual(('running', '1', '4'), (row['state'], row['resumed'], row['tools']))


if __name__ == '__main__':
    unittest.main()
