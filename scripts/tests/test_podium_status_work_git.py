"""Layer 3 of the Status box (user decision 16/11/2026), the part that asks git: at an agent's stop its work list is rebuilt
from its transcript and each kept entry is marked with what git says now, and a commit is trusted only when the repository
has it with a time inside the tool call that printed it. Real repositories in a temporary folder; the hooks run as
commands, as test_podium_status_agents.py.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import podium_status_work as work  # noqa: E402
import test_podium_status_agents as base  # noqa: E402

SEP = work.SEPARATOR
GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main']


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def call(ident, name, given, at, cwd):
    return {'type': 'assistant', 'cwd': cwd, 'timestamp': stamp(at),
            'message': {'content': [{'type': 'tool_use', 'id': ident, 'name': name, 'input': given}]}}


def result(ident, at, content='', error=False):
    return {'type': 'user', 'timestamp': stamp(at),
            'message': {'content': [{'type': 'tool_result', 'tool_use_id': ident, 'content': content, 'is_error': error}]}}


class RepoCase(unittest.TestCase):
    """A repository with one commit: kept.txt, sub/deep.txt, [id].tsx, :x.txt and a .gitignore for ignored.log. No tests here."""
    def setUp(self):
        self.repo = os.path.realpath(tempfile.mkdtemp())
        self.git('init', '-q')
        self.write('kept.txt', 'a')
        self.write('.gitignore', 'ignored.log\n')
        self.write('sub/deep.txt', 'a')
        self.write('[id].tsx', 'a')
        self.write(':x.txt', 'a')
        self.git('add', '-A')
        self.git('commit', '-qm', 'first')
        self.deadline = time.monotonic() + 30

    def git(self, *args):
        return subprocess.run(GIT + list(args), cwd=self.repo, capture_output=True, text=True, check=True).stdout

    def write(self, name, text):
        path = os.path.join(self.repo, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        return path

    def head(self):
        return self.git('log', '-1', '--format=%H %ct').split()


class Marks(RepoCase):
    def test_an_edited_file_is_marked_with_what_git_says_now(self):
        self.assertEqual('', work.edit_mark(os.path.join(self.repo, 'kept.txt'), self.deadline))
        self.assertEqual(work.UNCOMMITTED, work.edit_mark(self.write('kept.txt', 'b'), self.deadline))
        self.assertEqual(work.UNCOMMITTED, work.edit_mark(self.write('new.txt', 'x'), self.deadline))
        self.assertEqual(work.UNCOMMITTED, work.edit_mark(self.write('sub/deep.txt', 'b'), self.deadline))   # path from the top
        self.assertEqual(work.IGNORED, work.edit_mark(self.write('ignored.log', 'x'), self.deadline))

    def test_a_file_name_is_never_a_pattern(self):
        # `[id].tsx` as a pathspec matches i.tsx and d.tsx; the clean file itself must not take their change.
        self.write('i.tsx', 'changed')
        self.assertEqual('', work.edit_mark(os.path.join(self.repo, '[id].tsx'), self.deadline))
        # `:x.txt` as a pathspec is x.txt (magic): the changed file itself must still be seen.
        self.assertEqual(work.UNCOMMITTED, work.edit_mark(self.write(':x.txt', 'changed'), self.deadline))

    def test_what_git_cannot_be_asked_about_is_not_checked(self):
        outside = tempfile.mkdtemp()
        self.assertEqual(work.UNCHECKED, work.edit_mark(os.path.join(outside, 'a.txt'), self.deadline))     # no repository
        self.assertEqual(work.UNCHECKED, work.edit_mark('/no/such/folder/a.txt', self.deadline))
        self.assertEqual(work.UNCHECKED, work.edit_mark(os.path.join(self.repo, 'kept.txt'), time.monotonic() - 1))
        self.assertIsNone(work.git('', self.deadline, 'status'))

    def test_commit_times_finds_a_known_sha_by_its_prefix_and_skips_an_unknown_one(self):
        sha, when = self.head()
        found = work.commit_times([sha[:7], 'deadbee'], ['/no/such', self.repo], self.deadline)
        self.assertEqual({sha[:7]: int(when)}, found)
        self.assertEqual({}, work.commit_times([sha[:7]], [], self.deadline))

    def test_a_commit_is_trusted_only_when_made_inside_the_call_that_printed_it(self):
        sha, when = self.head()
        when = int(when)

        def item(key, window):
            return ('commit', key, 'commit x', self.repo, window)
        self.assertEqual(['commit x'], work.marked([item(sha[:7], (when - 1, when + 1))]))
        self.assertEqual(['commit x'], work.marked([item(sha[:7], None)]))                       # no times: the sha alone
        self.assertEqual(['commit x'], work.marked([item(sha[:7], (when + work.SLACK, when + work.SLACK))]))   # edge
        late = when + work.SLACK + 1
        self.assertEqual(['commit x' + work.UNVERIFIED], work.marked([item(sha[:7], (late, late + 5))]))
        early = when - work.SLACK - 6
        self.assertEqual(['commit x' + work.UNVERIFIED], work.marked([item(sha[:7], (early, early + 5))]))
        self.assertEqual(['commit x' + work.UNVERIFIED], work.marked([item('deadbee', None)]))
        self.assertEqual([work.NO_SHA + work.UNVERIFIED], work.marked([('commit', None, work.NO_SHA, self.repo, None)]))

    def test_a_commit_is_found_through_an_edited_file_folder_when_its_own_folder_is_gone(self):
        sha, _ = self.head()
        items = [('edit', os.path.join(self.repo, 'kept.txt'), 'edited kept.txt', '/gone', None),
                 ('commit', sha[:7], 'commit x', '/gone', None)]
        self.assertEqual(['edited kept.txt', 'commit x'], work.marked(items))


class Transcript(RepoCase):
    def transcript(self, lines, raw=()):
        self.count = getattr(self, 'count', 0) + 1
        path = os.path.join(tempfile.mkdtemp(), 'agent-%d.jsonl' % self.count)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join([json.dumps(line) for line in lines] + list(raw)) + '\n')
        return path

    def test_the_stop_rebuilds_the_list_from_every_successful_call_in_order(self):
        sha, when = self.head()
        now = int(when)
        lines = [call('a', 'Edit', {'file_path': 'kept.txt'}, now, self.repo), result('a', now),
                 call('b', 'Edit', {'file_path': 'bad.txt'}, now, self.repo), result('b', now, error=True),
                 call('c', 'Bash', {'command': 'git commit -m first'}, now, self.repo),
                 result('c', now + 1, '[main %s] first' % sha[:7]),
                 call('d', 'Edit', {'file_path': 'kept.txt'}, now, self.repo), result('d', now),           # again: to the end
                 {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 5, 'name': 'Edit',
                                                                'input': {'file_path': '/x'}}]}}]
        found = work.read_transcript(self.transcript(lines, raw=['not json', '[]']))
        self.assertEqual([('commit', sha[:7]), ('edit', os.path.join(self.repo, 'kept.txt'))], [i[:2] for i in found[0]])
        self.assertEqual((now, now + 1), found[0][0][4])
        self.assertEqual('commit %s first%sedited kept.txt' % (sha[:7], SEP), work.from_transcript(self.transcript(lines)))

    def test_the_newest_five_are_kept_and_the_rest_counted(self):
        lines = []
        for n in range(7):
            self.write('f%d.txt' % n, 'x')
            lines += [call('e%d' % n, 'Write', {'file_path': os.path.join(self.repo, 'f%d.txt' % n)}, 0, self.repo), result('e%d' % n, 0)]
        entries = work.from_transcript(self.transcript(lines)).split(SEP)
        self.assertEqual(['… 2 earlier'] + ['edited f%d.txt%s' % (n, work.UNCOMMITTED) for n in range(2, 7)], entries)

    def test_an_agent_that_changed_nothing_shows_its_report_marked_not_verified(self):
        report = {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'id': 'h', 'name': 'SubagentHandback', 'input': {'message': '## Review\nAll clean.'}}]}}
        last = {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'my last words'}]}}
        self.assertEqual(work.REPORTED + 'All clean.', work.from_transcript(self.transcript([report, last])))
        self.assertEqual(work.REPORTED + 'my last words', work.from_transcript(self.transcript([last])))
        user_text = {'type': 'user', 'message': {'content': [{'type': 'text', 'text': 'the prompt'}]}}
        self.assertEqual('', work.from_transcript(self.transcript([user_text])))

    def test_a_transcript_that_cannot_be_read_keeps_the_live_list(self):
        self.assertIsNone(work.from_transcript(''))
        self.assertIsNone(work.from_transcript('/no/such/agent.jsonl'))
        path = self.transcript([{'type': 'assistant'}])
        old, work.MAX_TRANSCRIPT = work.MAX_TRANSCRIPT, 5
        try:
            self.assertIsNone(work.from_transcript(path))
        finally:
            work.MAX_TRANSCRIPT = old


class Hooks(RepoCase):
    """The hooks end to end: live ticks fill `work`, the stop replaces it with the marked list."""
    setUp_rows = base.AgentRows.setUp
    run_hook, table, rows = base.AgentRows.run_hook, base.AgentRows.table, base.AgentRows.rows
    run_tool = base.AgentRows.run_tool

    def setUp(self):
        RepoCase.setUp(self)
        self.setUp_rows()

    def test_the_live_list_grows_with_each_call_and_the_stop_marks_it(self):
        agent = base.DEVELOPER
        self.run_hook('subagent', agent)
        path = self.write('kept.txt', 'changed')
        self.run_hook('tool', dict(agent, tool_name='Edit', tool_input={'file_path': path}, tool_response={}, cwd=self.repo))
        self.assertEqual('edited kept.txt', self.rows(base.DEVELOPER_NAME)[0]['work'])
        now = int(time.time())
        transcript = os.path.join(self.dir, 'agent.jsonl')
        with open(transcript, 'w', encoding='utf-8') as handle:
            for line in [call('a', 'Edit', {'file_path': path}, now, self.repo), result('a', now)]:
                handle.write(json.dumps(line) + '\n')
        self.run_hook('subagent-stop', dict(agent, agent_transcript_path=transcript))
        row = self.rows(base.DEVELOPER_NAME)[0]
        self.assertEqual(('done', 'edited kept.txt' + work.UNCOMMITTED), (row['state'], row['work']))
        self.run_hook('subagent', agent)                                           # a resume keeps the list
        self.assertEqual('edited kept.txt' + work.UNCOMMITTED, self.rows(base.DEVELOPER_NAME)[0]['work'])

    def test_an_unreadable_transcript_at_the_stop_keeps_the_live_list(self):
        agent = base.DEVELOPER
        self.run_hook('subagent', agent)
        self.run_hook('tool', dict(agent, tool_name='Write', tool_input={'file_path': '/r/a.txt'}, tool_response={}, cwd='/r'))
        self.run_hook('subagent-stop', dict(agent, agent_transcript_path='/no/such.jsonl'))
        self.assertEqual('edited a.txt', self.rows(base.DEVELOPER_NAME)[0]['work'])


if __name__ == '__main__':
    unittest.main()
