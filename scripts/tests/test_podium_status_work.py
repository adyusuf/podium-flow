"""Layer 3 of the Status box (user decision 16/11/2026): the work list under a subagent's row - what one tool call adds,
how the field is joined, kept short and kept honest. These tests call podium_status_work.py's functions directly; the
git marks and the hooks are in test_podium_status_work_git.py.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import podium_status_work as work  # noqa: E402

SEP = work.SEPARATOR
SHA = '1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b'


class Field(unittest.TestCase):
    def test_the_field_keeps_the_newest_five_and_counts_the_rest_at_the_stop_but_not_live(self):
        items = ['e%d' % n for n in range(7)]
        self.assertEqual(SEP.join(['… 2 earlier', 'e2', 'e3', 'e4', 'e5', 'e6']), work.joined(items))
        self.assertEqual(SEP.join(['… earlier', 'e2', 'e3', 'e4', 'e5', 'e6']), work.joined(items, live=True))
        self.assertEqual(SEP.join(['… 4 earlier', 'e2', 'e3', 'e4', 'e5', 'e6']), work.joined(items, dropped=2))
        self.assertEqual(SEP.join(['a', 'b']), work.joined(['a', 'b']))
        self.assertEqual(SEP.join(['… earlier', 'a']), work.joined(['a'], marker='… earlier'))
        self.assertEqual('', work.joined([]))

    def test_parse_splits_the_earlier_marker_from_the_entries(self):
        self.assertEqual(('… 3 earlier', ['a', 'b']), work.parse(SEP.join(['… 3 earlier', 'a', 'b'])))
        self.assertEqual(('… earlier', ['a']), work.parse(SEP.join(['… earlier', 'a'])))
        self.assertEqual(('', ['a', '… 3 earlier']), work.parse(SEP.join(['a', '… 3 earlier'])))   # only first
        self.assertEqual(('', ['a', 'b']), work.parse(SEP.join(['a', ' ', 'b', ''])))
        self.assertEqual(('', []), work.parse(None))

    def test_add_moves_a_repeated_entry_to_the_end_and_keeps_the_marker(self):
        text = work.add(work.add(work.add('', 'a'), 'b'), 'a')
        self.assertEqual(SEP.join(['b', 'a']), text)
        full = SEP.join(['… earlier'] + ['e%d' % n for n in range(5)])
        self.assertEqual(SEP.join(['… earlier', 'e1', 'e2', 'e3', 'e4', 'new']), work.add(full, 'new'))

    def test_untrusted_text_cannot_fake_an_entry_or_carry_control_or_bidi_marks(self):
        self.assertEqual('a b', work.safe('a' + SEP + 'b'))
        self.assertNotIn('‮', work.safe('x‮y'))
        self.assertNotIn('\x1b', work.safe('x\x1b[31my'))
        self.assertEqual('', work.safe(None))
        self.assertNotIn(SEP, work.committed(SHA, 'fake' + SEP + 'edited x'))
        self.assertNotIn(SEP, work.first_line('done' + SEP + 'edited x'))
        # A file named to look like a second entry stays one entry (QA F3, 16/11/2026).
        self.assertNotIn(SEP, work.shown_path('/r/a' + SEP + 'commit 1234567 x', '/r'))
        self.assertNotIn(SEP, work.new_items('Edit', {'file_path': '/r/a' + SEP + 'commit 1234567 x'}, None, '/r')[0][2])


class Shown(unittest.TestCase):
    def test_a_path_is_shown_relative_to_the_agent_folder_or_home_and_a_long_one_keeps_its_end(self):
        self.assertEqual('src/a.ts', work.shown_path('/repo/src/a.ts', '/repo/'))
        self.assertEqual('/other/a.ts', work.shown_path('/other/a.ts', '/repo'))
        self.assertEqual('/repository/a.ts', work.shown_path('/repository/a.ts', '/repo'))   # not a prefix match
        home = os.path.expanduser('~')
        self.assertEqual('~/x/a.ts', work.shown_path(home + '/x/a.ts', ''))
        long = '/repo/' + 'd/' * 60 + 'end.ts'
        shown = work.shown_path(long, '')
        room = work.ENTRY - len('edited ') - len(work.IGNORED)
        self.assertEqual(room, len(shown))
        self.assertTrue(shown.startswith('…') and shown.endswith('d/end.ts'))
        # With the longest mark the stop adds, an edit entry still fits its share of the field.
        self.assertLessEqual(len('edited ' + shown + work.IGNORED), work.ENTRY)

    def test_a_commit_shows_seven_characters_of_its_sha_and_fits_with_its_mark(self):
        self.assertEqual('commit 1a2b3c4 fix the thing', work.committed(SHA, 'fix the thing'))
        self.assertEqual(work.NO_SHA, work.committed(None, 'whatever'))
        self.assertEqual(work.ENTRY - len(work.UNVERIFIED), len(work.committed(SHA, 'x' * 500)))

    def test_every_entry_and_the_marker_fit_the_field(self):
        entries = [work.committed(SHA, 'x' * 500) + work.UNVERIFIED for _ in range(9)]
        self.assertLessEqual(len(work.joined(entries)), work.MAX_WORK)


class Commands(unittest.TestCase):
    def test_plain_drops_heredoc_bodies_and_empties_quoted_strings(self):
        self.assertEqual('cat <<EOF\nnext', work.plain("cat <<EOF\ngit commit -m x\nEOF\nnext"))
        self.assertEqual("cat <<-\"\"\nnext", work.plain("cat <<-'END'\ngit commit\n  END\nnext"))
        self.assertEqual('echo "" ""', work.plain('echo "git commit" \'git commit\''))
        self.assertEqual('echo ""', work.plain('echo "a \\" git commit"'))
        self.assertEqual('echo "" x', work.plain('echo "one\ngit commit\ntwo" x'))      # a quote over lines
        self.assertEqual('a <<< x', work.plain('a <<< x'))                               # a here-string has no body

    def test_only_a_git_commit_where_a_command_starts_counts(self):
        out = '[feat/x 1a2b3c4] the subject\n 1 file changed'
        counted = ['git commit -m "x"', 'cd a && git commit -am x', 'git -C /r commit -m x', '/usr/bin/git commit -m x',
                   'env A=1 git commit -m x', 'A=1 git commit -m x', 'if x; then git commit -m y; fi', '(git commit -m x)',
                   'git --no-pager -c a=b commit -m x', 'true; git commit -m x', 'sudo -E git commit -m x']
        for command in counted:
            with self.subTest(command=command):
                self.assertEqual([('1a2b3c4', 'the subject')], work.commits_of(command, out))
        ignored = ['grep "git commit" f', "echo 'git commit'", 'git commit-tree x', 'git log --grep commit',
                   'cat <<EOF\ngit commit -m x\nEOF', 'mygit commit -m x', 'git status', None, 42]
        for command in ignored:
            with self.subTest(command=command):
                self.assertEqual([], work.commits_of(command, out))

    def test_a_commit_that_printed_no_sha_is_one_with_none(self):
        self.assertEqual([(None, '')], work.commits_of('git commit -qm x', ''))
        self.assertEqual([(None, '')], work.commits_of('git commit -qm x', 'nothing to commit'))

    def test_every_commit_line_counts_including_root_and_detached(self):
        out = '[main (root-commit) abcdef1] first\n[detached HEAD 1234567] second\n'
        self.assertEqual([('abcdef1', 'first'), ('1234567', 'second')], work.commits_of('git commit -m a; git commit -m b', out))

    def test_a_log_after_a_quiet_commit_gives_its_sha_only_when_it_runs_after_it(self):
        out = 'abcdef1 the subject\n0000000 older'
        for command in ('git commit -qm "the subject" && git log --oneline -1', "git commit -qm 'the subject'; git log -1",
                        'git commit -qF msg.txt\ngit log --oneline -1'):
            with self.subTest(command=command):
                self.assertEqual([('abcdef1', 'the subject')], work.commits_of(command, out))
        for command in ('git commit -qm x || git log --oneline -1', 'git commit -qm x | git log --oneline -1',
                        'git commit -qm x & git log --oneline -1', 'git log --oneline -1; git commit -qm x'):
            with self.subTest(command=command):
                self.assertEqual([(None, '')], work.commits_of(command, out))

    def test_commit_lines_win_over_a_log_line(self):
        out = '[b 1234567] real\nabcdef1 log line'
        self.assertEqual([('1234567', 'real')], work.commits_of('git commit -m x && git log --oneline -1', out))


class OpenFindings(unittest.TestCase):
    """The layer 3 open findings closed on 17/11/2026: L1 and L2 of QA pass 3, and Windows paths."""

    def test_the_log_line_is_the_commits_own_when_the_command_shows_its_message(self):
        out = '1111111 another commit\nabcdef1 the subject\n'
        for command in ('git commit -qm "the subject" && git log --oneline -2',
                        "git commit -q -m 'the subject' && git log -2",
                        'git commit -q --message="the subject" && git log -2',
                        "git commit -q -m \"$(cat <<'EOF'\nthe subject\n\nthe body\nEOF\n)\" && git log --oneline -2",
                        'grep -m 1 x f; git commit -qm "the subject" && git log -2'):     # an earlier -m is not it
            with self.subTest(command=command):
                self.assertEqual([('abcdef1', 'the subject')], work.commits_of(command, out))
        # A message the log does not show gives no sha rather than another commit's; an unknown one keeps the first line.
        self.assertEqual([(None, '')], work.commits_of('git commit -qm "not there" && git log -2', out))
        for command in ('git commit -qF msg && git log -2', 'git commit -qm "$MSG" && git log -2'):
            with self.subTest(command=command):
                self.assertEqual([('1111111', 'another commit')], work.commits_of(command, out))

    def test_the_subject_is_the_first_paragraph_on_one_line(self):
        self.assertEqual('one two', work.subject('git commit -m "one\n  two\n\nbody"'))
        self.assertEqual('say "hi"', work.subject('git commit -m "say \\"hi\\""'))
        self.assertEqual('a$b', work.subject("git commit -m 'a$b'"))                    # single quotes do not expand
        self.assertEqual('word', work.subject('git commit -qm word && x'))
        self.assertIsNone(work.subject('git commit -m "$(git log -1)"'))
        self.assertIsNone(work.subject('git commit -m "   "'))
        self.assertIsNone(work.subject('git commit -F file'))

    def test_a_comment_an_escaped_quote_and_a_dry_run_are_not_commits(self):
        out = '[b 1a2b3c4] s'
        for command in ('git status  # then git commit', '# git commit -m x', "echo it\\'s; echo 'x; git commit'",
                        'git commit --dry-run -m x', 'git commit -m x --dry-run && echo ok'):
            with self.subTest(command=command):
                self.assertEqual([], work.commits_of(command, out))
        self.assertEqual([('1a2b3c4', 's')], work.commits_of("echo it\\'s && git commit -m x", out))
        self.assertEqual([('1a2b3c4', 's')], work.commits_of('git commit --dry-run; git commit -m y', out))
        self.assertEqual('echo a#b ', work.plain('echo a#b # c'))                       # # inside a word is no comment

    def test_on_windows_either_slash_and_any_case_take_the_folder_off(self):
        original = work.WINDOWS
        self.addCleanup(setattr, work, 'WINDOWS', original)
        work.WINDOWS = True
        self.assertEqual('src\\a.ts', work.shown_path('C:\\r\\src\\a.ts', 'C:\\r'))
        self.assertEqual('a.ts', work.shown_path('c:/R/a.ts', 'C:\\r\\'))
        self.assertEqual('C:\\repository\\a', work.shown_path('C:\\repository\\a', 'C:\\repo'))   # not a prefix match
        self.assertEqual('C:\\r\\', work.shown_path('C:\\r\\', 'C:\\r'))                     # the folder itself
        work.WINDOWS = False                                                       # elsewhere \ is part of a name
        self.assertEqual('C:\\r\\a', work.shown_path('C:\\r\\a', 'C:\\r'))
        self.assertEqual('/R/a', work.shown_path('/R/a', '/r'))


class ToolCalls(unittest.TestCase):
    def test_an_edit_is_keyed_by_its_absolute_path_and_shown_relative(self):
        self.assertEqual([('edit', os.path.join('/r', 'src/a.ts'), 'edited src/a.ts', '/r')],
                         work.new_items('Edit', {'file_path': 'src/a.ts'}, None, '/r'))
        self.assertEqual([('edit', '/x/n.ipynb', 'edited /x/n.ipynb', '/r')],
                         work.new_items('NotebookEdit', {'notebook_path': '/x/n.ipynb'}, None, '/r'))
        for tool in work.EDIT_TOOLS:
            self.assertEqual('edit', work.new_items(tool, {'file_path': '/a'}, None, '')[0][0])
        self.assertEqual([], work.new_items('Edit', {}, None, '/r'))
        self.assertEqual([], work.new_items('Edit', {'file_path': 7}, None, '/r'))
        self.assertEqual([], work.new_items('Edit', 'not a dict', None, '/r'))
        self.assertEqual([], work.new_items('Read', {'file_path': '/a'}, None, '/r'))

    def test_a_bash_commit_is_keyed_by_its_sha(self):
        items = work.new_items('Bash', {'command': 'git commit -m x'}, {'stdout': '[b 1234567] x'}, '/r')
        self.assertEqual([('commit', '1234567', 'commit 1234567 x', '/r')], items)
        self.assertEqual([], work.new_items('Bash', {'command': 'ls'}, {'stdout': '[b 1234567] x'}, '/r'))

    def test_result_text_reads_every_shape_a_tool_result_comes_in(self):
        self.assertEqual('s', work.result_text('s'))
        self.assertEqual('out\nmore', work.result_text({'stdout': 'out', 'content': 'more'}))
        self.assertEqual('out\n', work.result_text({'stdout': 'out', 'content': ['not a string']}))
        self.assertEqual('a\nb', work.result_text([{'type': 'text', 'text': 'a'}, 'junk', {'text': 'b'}]))
        self.assertEqual('', work.result_text(None))

    def test_live_each_call_adds_what_its_payload_shows_and_a_failed_call_adds_nothing(self):
        edit = {'tool_name': 'Edit', 'tool_input': {'file_path': '/r/a.ts'}, 'tool_response': {}, 'cwd': '/r'}
        text = work.add_live('', edit)
        self.assertEqual('edited a.ts', text)
        self.assertEqual('edited a.ts', work.add_live(text, edit))                          # once, not twice
        failed = dict(edit, tool_input={'file_path': '/r/b.ts'}, tool_response={'is_error': True})
        self.assertEqual(text, work.add_live(text, failed))
        self.assertEqual('', work.add_live(None, failed))
        self.assertEqual('', work.add_live(None, {'tool_name': 'Read'}))
        commit = {'tool_name': 'Bash', 'tool_input': {'command': 'git commit -m m'}, 'tool_response': {'stdout': '[b 7654321] m'}}
        self.assertEqual(SEP.join(['edited a.ts', 'commit 7654321 m']), work.add_live(text, commit))


class Report(unittest.TestCase):
    def test_the_first_line_that_says_something_is_kept_in_its_own_words_and_marked(self):
        report = '# QA report\n\n---\n> **Result:** `serious_gap` NO\nmore'
        self.assertEqual(work.REPORTED + 'Result: serious_gap NO', work.first_line(report))
        self.assertEqual(work.REPORTED + 'item one', work.first_line('- item one'))
        self.assertEqual(work.REPORTED + 'Result', work.first_line('Result:'))
        self.assertEqual(work.REPORTED + 'a | b', work.first_line('| a | b |'))
        self.assertEqual('', work.first_line('# only a heading\n\n==='))
        self.assertEqual('', work.first_line(None))
        self.assertEqual(work.ENTRY, len(work.first_line('x' * 500)))

    def test_epoch_reads_a_transcript_timestamp_and_nothing_else(self):
        self.assertEqual(0, work.epoch('1970-01-01T00:00:00.000Z'))
        self.assertEqual(86400, work.epoch('1970-01-02T00:00:00Z'))
        for stamp in (None, '', 'yesterday'):
            self.assertIsNone(work.epoch(stamp))


if __name__ == '__main__':
    unittest.main()
