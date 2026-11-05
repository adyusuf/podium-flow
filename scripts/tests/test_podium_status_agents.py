"""The Status box's rows for subagents are written by the hooks, not by the agent (user decision 05/11/2026): a row opens at
SubagentStart, counts tool calls, and closes at SubagentStop as done or failed, with only measured figures; `drop` and
`--after` find a step by a prefix of its name, `rename` renames in place, `now` is the name of the step at work.

Each test runs the scripts as commands with the status folder in a temporary directory, so no real file is read or written.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(SCRIPTS, 'podium_status.py')
SESSION = 'abc-123'
WRITER = {'session_id': SESSION, 'agent_type': 'podium:doc-writer', 'agent_id': 'c0ffee1234'}       # no Bash tool
WRITER_NAME = 'podium:doc-writer c0ffee'
DEVELOPER = {'session_id': SESSION, 'agent_type': 'podium:developer', 'agent_id': 'a849d9ffff'}
DEVELOPER_NAME = 'podium:developer a849d9'


class AgentRows(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.env = dict(os.environ, PODIUM_STATUS_DIR=self.dir, PODIUM_CONFIG_USER=os.path.join(self.dir, 'u.json'),
                        PODIUM_SESSION_DIR=os.path.join(self.dir, 'sessions'))

    def run_tool(self, *args):
        done = subprocess.run([sys.executable, SCRIPT, '--session', SESSION, *args], env=self.env, capture_output=True, text=True)
        return done.stdout, done.stderr, done.returncode

    def run_hook(self, event, payload):
        done = subprocess.run([sys.executable, SCRIPT, 'hook', event], env=self.env, capture_output=True,
                              input=json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        return done.stdout.decode(), done.stderr.decode(), done.returncode

    def table(self):
        return json.loads(self.run_tool('show', '--json')[0])

    def rows(self, agent=None):
        return [row for row in self.table()['rows'] if agent is None or row['agent'] == agent]

    def age(self, agent, seconds):
        """Make the agent's row start `seconds` ago, so a duration is known without sleeping."""
        path = os.path.join(self.dir, SESSION + '.json')
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        for row in data['rows']:
            if row['agent'] == agent:
                row['since'] = str(int(time.time()) - seconds)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle)

    def transcript(self, lines):
        path = os.path.join(self.dir, 'agent.jsonl')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(json.dumps(line) for line in lines) + '\n')
        return path

    # --- the hooks write the row -------------------------------------------------------------------------------------

    def test_an_agent_without_bash_is_visible_while_it_runs_and_after_it_ends_with_no_invented_percent(self):
        self.run_hook('subagent', WRITER)
        row = self.rows(WRITER_NAME)[0]
        self.assertEqual(('task', 'running', ''), (row['item'], row['state'], row['percent']))   # no signal, no %
        self.assertIn(WRITER_NAME + ' | task | running', self.run_tool('show')[0])
        self.run_hook('subagent-stop', dict(WRITER, duration_ms=125000, tool_uses=7))
        row = self.rows(WRITER_NAME)[0]
        self.assertEqual(('done', '100', '2m05s · 7 tool uses'), (row['state'], row['percent'], row['note']))
        self.assertIn(WRITER_NAME + ' | task | done | 100%', self.run_tool('show')[0])

    def test_a_running_row_counts_the_agents_tool_calls_and_the_time_since_it_started(self):
        self.run_hook('subagent', dict(DEVELOPER, model='sonnet'))
        self.age(DEVELOPER_NAME, 65)
        for _ in range(3):
            self.run_hook('tool', dict(DEVELOPER, tool_name='Read'))
        self.run_hook('tool', {'session_id': SESSION, 'tool_name': 'Read'})          # a call of the session itself: no agent
        row = self.rows(DEVELOPER_NAME)[0]
        self.assertEqual(('running', '', '3'), (row['state'], row['percent'], row['tools']))
        self.assertRegex(row['note'], r'^sonnet · 1m0[5-9]s · 3 tool uses$')       # 65 s ago, a little slack for the calls
        self.assertEqual([DEVELOPER_NAME], [r['agent'] for r in self.rows() if r['agent']])      # nothing else was written

    def test_two_agents_of_one_kind_keep_their_own_rows(self):
        other = dict(DEVELOPER, agent_id='b00b00b00b')
        self.run_hook('subagent', DEVELOPER)
        self.run_hook('subagent', other)
        self.run_hook('subagent-stop', dict(DEVELOPER, tool_uses=1))
        self.assertEqual(['done', 'running'], [r['state'] for r in self.rows() if r['agent']])

    def test_a_stop_with_figures_the_payload_lacks_reads_them_from_the_transcript_without_counting_a_line_twice(self):
        def line(message_id, out, *calls):          # a message may be written on several lines, the same id on each
            blocks = [{'type': 'tool_use', 'id': call} for call in calls] or [{'type': 'text'}]
            return {'type': 'assistant', 'message': {'id': message_id, 'usage': {'output_tokens': out}, 'content': blocks}}
        path = self.transcript([line('m1', 10, 't1'), line('m1', 40, 't1', 't2'), line('m2', 1960), 'not a message', {'type': 'user'}])
        self.run_hook('subagent', DEVELOPER)
        self.age(DEVELOPER_NAME, 30)
        self.run_hook('subagent-stop', dict(DEVELOPER, agent_transcript_path=path))
        self.assertRegex(self.rows(DEVELOPER_NAME)[0]['note'], r'^3[0-4]s · 2 tool uses · 2\.0k out tokens$')

    def test_a_figure_nothing_measured_is_left_out_not_estimated(self):
        self.run_hook('subagent-stop', dict(WRITER, agent_transcript_path=os.path.join(self.dir, 'missing.jsonl')))
        row = self.rows(WRITER_NAME)[0]       # it never started under the hooks: no start time, no count, no transcript
        self.assertEqual(('done', ''), (row['state'], row['note']))

    def test_zero_calls_seen_by_the_hooks_is_not_reported_as_a_count(self):
        self.run_hook('subagent', DEVELOPER)
        self.run_hook('subagent-stop', DEVELOPER)
        self.assertNotIn('tool use', self.rows(DEVELOPER_NAME)[0]['note'])

    # --- a failure stays ---------------------------------------------------------------------------------------------

    def test_an_agent_that_ends_in_error_stays_as_a_failed_row_with_its_reason(self):
        self.run_hook('subagent', DEVELOPER)
        self.run_hook('subagent-stop', dict(DEVELOPER, error='tool crashed', tool_uses=4))
        self.run_hook('subagent', WRITER)
        self.run_hook('subagent-stop', dict(WRITER, status='cancelled'))
        failed = {row['agent']: row for row in self.rows() if row['agent']}
        mine = failed[DEVELOPER_NAME]
        self.assertEqual(('failed', '', 'tool crashed'), (mine['state'], mine['percent'], mine['blocker']))
        self.assertEqual(('failed', 'cancelled'), (failed[WRITER_NAME]['state'], failed[WRITER_NAME]['blocker']))
        self.assertIn('4 tool uses', failed[DEVELOPER_NAME]['note'])
        self.run_tool('step', 's' + 'x' * 5, 'done', '100')       # later writes do not remove it
        self.assertEqual(2, len([r for r in self.rows() if r['state'] == 'failed']))

    def test_a_failed_row_is_the_last_agent_row_a_full_table_gives_up(self):
        self.run_hook('subagent', DEVELOPER)
        self.run_hook('subagent-stop', dict(DEVELOPER, is_error=True))
        for number in range(60):
            self.run_hook('subagent', dict(WRITER, agent_id='%06d' % number))
            self.run_hook('subagent-stop', dict(WRITER, agent_id='%06d' % number))
        rows = self.rows()
        self.assertEqual(50, len(rows))
        self.assertIn('failed', [row['state'] for row in rows])

    def test_the_agents_own_steps_still_open_end_with_it(self):
        self.run_hook('subagent', DEVELOPER)
        self.run_tool('step', '1. Align devDependencies', 'running', '10', '--agent', DEVELOPER_NAME)       # an older-style row
        self.run_hook('subagent-stop', dict(DEVELOPER, tool_uses=2))
        own = self.rows(DEVELOPER_NAME)
        self.assertEqual({'done'}, {row['state'] for row in own})
        self.run_hook('subagent', WRITER)
        self.run_tool('step', 'draft', 'running', '10', '--agent', WRITER_NAME)
        self.run_hook('subagent-stop', dict(WRITER, error='x'))
        self.assertEqual({'failed'}, {row['state'] for row in self.rows(WRITER_NAME)})

    def test_an_agent_that_began_before_the_hooks_were_installed_is_still_closed(self):
        self.run_tool('step', 'old step', 'running', '10', '--agent', DEVELOPER_NAME)
        self.run_hook('subagent-stop', dict(DEVELOPER, tool_uses=1))
        self.assertEqual({'done'}, {row['state'] for row in self.rows(DEVELOPER_NAME)})

    # --- the steps guard sees the hook row ---------------------------------------------------------------------------

    def test_a_subagent_with_only_its_hook_row_may_edit_but_a_stranger_may_not(self):
        code = {'file_path': os.path.join(SCRIPTS, 'x.py')}
        guard = lambda who: self.run_hook('guard', dict(who, tool_name='Edit', tool_input=code))[2]  # noqa: E731
        self.assertEqual(2, guard(WRITER))                    # no step of any kind yet
        self.run_hook('subagent', WRITER)
        self.assertEqual(0, guard(WRITER))
        self.assertEqual(2, guard(DEVELOPER))                 # its row is not the writer's
        self.run_hook('subagent-stop', dict(WRITER))
        self.assertEqual(2, guard(WRITER))                    # an ended agent leaves nothing open

    # --- now, --after, drop, rename ----------------------------------------------------------------------------------

    def test_now_is_the_name_of_the_step_at_work_never_the_raw_message(self):
        self.run_hook('prompt', {'session_id': SESSION, 'prompt': 'ajanlar session hizasınd ayrı ayrı görünsün'})
        self.assertEqual('analysing the request', self.table()['now'])
        self.run_tool('step', '1. read', 'running', '10')
        self.run_tool('step', '2. build', 'not started', '0')
        self.assertEqual('1. read', self.table()['now'])
        self.run_tool('step', '1. read', 'done', '100')
        self.run_tool('step', '2. build', 'running', '30')
        self.assertEqual('2. build', self.table()['now'])
        self.run_hook('prompt', {'session_id': SESSION, 'prompt': 'one more thing'})
        self.assertEqual('2. build', self.table()['now'])
        self.run_hook('stop', {'session_id': SESSION})
        self.assertEqual('waiting for you', self.table()['now'])

    def test_after_finds_its_step_whoever_runs_it_so_an_agent_step_is_not_sent_to_the_end(self):
        for step in ('1. plan', '2. build', '3. ship'):
            self.run_tool('step', step, 'not started', '0')
        self.run_tool('step', 'align', 'running', '10', '--agent', DEVELOPER_NAME, '--after', '2. build')
        self.run_tool('step', '2a. check', 'not started', '0', '--after', '2. b')        # a prefix is enough
        self.assertEqual(['1. plan', '2. build', '2a. check', 'align', '3. ship'], [row['item'] for row in self.rows()])

    def test_drop_takes_an_exact_name_or_a_unique_prefix_and_refuses_an_ambiguous_one(self):
        for step in ('1. read the code', '2. write the code', '2b. write the tests'):
            self.run_tool('step', step, 'not started', '0')
        self.run_tool('step', 'task', 'running', '', '--agent', DEVELOPER_NAME)
        self.assertEqual(0, self.run_tool('drop', '1. rea')[2])
        out, err, code = self.run_tool('drop', '2')
        self.assertEqual(2, code)
        self.assertIn('names 2 steps', err)
        self.assertEqual(['2. write the code', '2b. write the tests', 'task'], [row['item'] for row in self.rows()])
        self.assertEqual(0, self.run_tool('drop', 'ta', '--agent', 'podium:developer')[2])       # the agent by a prefix too
        self.assertEqual(0, self.run_tool('drop', 'no such step')[2])                            # nothing named, nothing done
        self.assertEqual(['2. write the code', '2b. write the tests'], [row['item'] for row in self.rows()])

    def test_an_exact_name_wins_over_a_longer_name_that_starts_with_it(self):
        for step in ('build', 'build the api'):
            self.run_tool('step', step, 'not started', '0')
        self.run_tool('drop', 'build')
        self.assertEqual(['build the api'], [row['item'] for row in self.rows()])

    def test_rename_changes_the_name_in_place_and_keeps_everything_else(self):
        self.run_tool('step', '1. plan', 'running', '40', '--note', 'a note', '--blocker', 'qa')
        self.run_tool('step', '2. build', 'not started', '0')
        self.assertEqual(0, self.run_tool('rename', '1. pl', '1. plan the work')[2])
        self.assertEqual([('1. plan the work', 'running', '40', 'a note', 'qa'), ('2. build', 'not started', '0', '', '')],
                         [(r['item'], r['state'], r['percent'], r['note'], r['blocker']) for r in self.rows()])
        self.assertEqual('1. plan the work', self.table()['now'])
        for args in (('nothing', 'x'), ('1.', 'x', '--agent', 'nobody'), ('1. plan the work', '2. build'), ('1. plan the work', '')):
            self.assertEqual(2, self.run_tool('rename', *args)[2], args)
        self.run_tool('step', 'work', 'running', '', '--agent', DEVELOPER_NAME)
        self.assertEqual(0, self.run_tool('rename', 'wo', 'task', '--agent', DEVELOPER_NAME)[2])
        self.assertEqual(['task'], [r['item'] for r in self.rows(DEVELOPER_NAME)])

    # --- older data keeps working ------------------------------------------------------------------------------------

    def test_a_table_written_by_the_older_script_loads_and_an_older_step_command_still_works(self):
        old = {'now': 'working on: x', 'next': '', 'updated': '2026-11-02T00:00:00Z', 'rows': [
            {'item': 'gate', 'state': 'running', 'figure': '1 step', 'waiting': '-'},
            {'item': '1. read', 'state': 'running', 'figure': '10%', 'waiting': '', 'percent': '10', 'blocker': '',
             'agent': 'podium:developer a849d9'}]}
        with open(os.path.join(self.dir, SESSION + '.json'), 'w', encoding='utf-8') as handle:
            json.dump(old, handle)
        self.assertEqual(['gate', '1. read'], [r['item'] for r in self.rows()])
        self.assertIn('podium:developer a849d9 | 1. read | running | 10%', self.run_tool('show')[0])
        self.assertEqual(0, self.run_tool('drop', '1. read', '--agent', 'podium:developer a849d9')[2])
        self.assertEqual(0, self.run_tool('step', '2. new', 'failed', '0', '--blocker', 'why')[2])
        self.assertEqual(('failed', 'why'), (self.rows()[-1]['state'], self.rows()[-1]['blocker']))


if __name__ == '__main__':
    unittest.main()
