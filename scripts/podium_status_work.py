"""Layer 3 of the Status box (user decision 16/11/2026; order: state, then agent, then the agent's own work): the work
list under a subagent's row, kept in the row's `work` field.

    edited <path>             a file the agent changed with Edit/Write/NotebookEdit, a call that did not fail
    commit <sha> <subject>    a commit a successful `git commit` printed - git's own `[branch sha] subject` line, or for
                              `git commit -q ... && git log --oneline -1` the log's first line; `commit, sha not printed`
                              when it printed neither
    reported, not verified: <first sentence of its report>
                              only for an agent that edited and committed nothing (a review): its own words, never a
                              measurement

Live, each tool call of the agent adds what its payload shows (`add_live`), with no marks. At the stop the list is
rebuilt from the agent's transcript, which holds every run (`from_transcript`); the newest MAX_ENTRIES are kept (a file
edited again moves to the end), `… N earlier` first when more were seen, and git is asked about the kept ones only,
within GIT_BUDGET seconds in all:
    edited ...: `(uncommitted)` git still shows a change · `(ignored by git)` · no mark: git shows no change left ·
                `(not checked)` git could not be asked (not a repository, the folder gone, out of time)
    commit ...: `(not verified)` when no repository it could be in knows the sha (or none could be asked)
A live list that dropped entries shows `… earlier` with no number: it cannot count what it dropped.

The field is one line of at most MAX_WORK characters: entries joined by SEPARATOR, each at most ENTRY characters with
its mark (a path keeps its end). SEPARATOR is taken out of every untrusted text, so a path, a commit subject or a report
cannot fake an entry; `clip` takes out control and bidirectional characters.
"""
import json
import os
import re
import subprocess
import time

from podium_status_rows import MAX_WORK, clip

SEPARATOR = '␞'          # a printable character (the record-separator sign), so the row's clip keeps it
MAX_ENTRIES = 5
ENTRY = MAX_WORK // (MAX_ENTRIES + 1) - 1     # every entry, the `… N earlier` one and the separators fit MAX_WORK
EDIT_TOOLS = ('Edit', 'Write', 'MultiEdit', 'NotebookEdit')
# `git commit`'s first line: `[branch 1a2b3c4] subject`, `[main (root-commit) 1a2b3c4] s`, `[detached HEAD 1a2b3c4] s`.
COMMIT = re.compile(r'^\[[^\]\n]+ ([0-9a-f]{7,40})\] (.+)$', re.M)
ONELINE = re.compile(r'^([0-9a-f]{7,40}) (.+)$', re.M)
# `git` with its global options (`-C dir`, `-c k=v`, `--no-pager`), then the subcommand.
GIT_SUB = r'\bgit(?:\s+-[Cc]\s+\S+|\s+--?[\w-]+(?:=\S+)?)*\s+%s\b'
EARLIER = re.compile(r'^… (?:\d+ )?earlier$')
REPORTED = 'reported, not verified: '
NO_SHA = 'commit, sha not printed'
UNCOMMITTED, IGNORED, UNCHECKED, UNVERIFIED = ' (uncommitted)', ' (ignored by git)', ' (not checked)', ' (not verified)'
MAX_TRANSCRIPT = 64 * 1024 * 1024
GIT_SECONDS, GIT_BUDGET = 2, 4     # one git call, and all of them at a stop (the hook holds the session's lock)


def safe(text):
    """Untrusted text as one clean line with no SEPARATOR in it."""
    return clip(str(text or '').replace(SEPARATOR, ' '))


def parse(text):
    """(the `… earlier` entry or '', the entries kept) from a stored `work` field."""
    items = [one for one in str(text or '').split(SEPARATOR) if one.strip()]
    return (items[0], items[1:]) if items and EARLIER.match(items[0]) else ('', items)


def joined(items, marker='', live=False, dropped=0):
    """The stored field: the newest MAX_ENTRIES of `items` (all distinct), `… N earlier` first when some were dropped."""
    dropped += max(0, len(items) - MAX_ENTRIES)
    marker = ('… earlier' if live else '… %d earlier' % dropped) if dropped > 0 else marker
    return SEPARATOR.join(([marker] if marker else []) + items[-MAX_ENTRIES:])


def shown_path(path, cwd):
    """A path relative to the agent's folder when it is inside it, `~/...` under the home folder; a long one keeps its end."""
    path, cwd, home = safe(path), str(cwd or '').rstrip('/'), os.path.expanduser('~')
    if cwd and path.startswith(cwd + '/'):
        path = path[len(cwd) + 1:]
    elif path.startswith(home + '/'):
        path = '~' + path[len(home):]
    room = ENTRY - len('edited ') - len(IGNORED)          # room for the longest mark the stop may add
    return path if len(path) <= room else '…' + path[-(room - 1):]


def committed(sha, subject):
    return safe('commit %s %s' % (sha[:7], subject))[:ENTRY - len(UNVERIFIED)] if sha else NO_SHA


def add(text, entry):
    """The field with `entry` appended; an equal entry already there moves to the end instead of showing twice."""
    marker, items = parse(text)
    return joined([one for one in items if one != entry] + [entry], marker, live=True)


def result_text(value):
    """The text of a tool result: a string, the `stdout` of a Bash result, or the text blocks of a list."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return '%s\n%s' % (value.get('stdout') or '', value.get('content') if isinstance(value.get('content'), str) else '')
    if isinstance(value, list):
        return '\n'.join(str(block.get('text') or '') for block in value if isinstance(block, dict))
    return ''


def commits_of(command, output):
    """(sha, subject) of each commit a successful `git commit` printed; (None, '') when it printed no sha."""
    if not isinstance(command, str) or not re.search(GIT_SUB % 'commit', command):
        return []
    found = COMMIT.findall(output)
    if not found and re.search(GIT_SUB % 'log', command):
        first = ONELINE.search(output)
        found = [first.groups()] if first else []
    return found or [(None, '')]


def new_items(tool, given, result, cwd):
    """What one tool call adds: (kind, key, shown text, folder) - an edited file (key: its absolute path) or a commit (key:
    its sha or None)."""
    given, cwd = (given if isinstance(given, dict) else {}), (cwd if isinstance(cwd, str) else '')
    if tool in EDIT_TOOLS:
        path = given.get('file_path') or given.get('notebook_path')
        if not isinstance(path, str) or not path:
            return []
        path = os.path.join(cwd, path) if cwd and not os.path.isabs(path) else path
        return [('edit', path, 'edited ' + shown_path(path, cwd), cwd)]
    if tool == 'Bash':
        return [('commit', sha, committed(sha, subject), cwd) for sha, subject in commits_of(given.get('command'), result_text(result))]
    return []


def add_live(text, payload):
    """The field after one PostToolUse of the agent, from what its payload shows."""
    response = payload.get('tool_response')
    if isinstance(response, dict) and response.get('is_error'):
        return text or ''
    for item in new_items(str(payload.get('tool_name') or ''), payload.get('tool_input'), response, payload.get('cwd')):
        text = add(text, item[2])
    return text or ''


def first_line(report):
    """`reported, not verified: <the first line of the report that says something>`, its words kept (no heading, no list or
    emphasis marks, no code ticks), or '' when it says nothing."""
    for line in str(report or '').splitlines():
        line = line.strip()
        if line.startswith('#'):          # a heading names the report; the first sentence says what it found
            continue
        line = re.sub(r'^[>*+\-\s]+', '', line).replace('**', '').replace('`', '').strip(' :|')
        if line and not re.fullmatch(r'[-=_*]{3,}', line):
            return safe(REPORTED + line)[:ENTRY]
    return ''


def read_transcript(path):
    """(items in order, latest last; the agent's report) from its transcript; None when it cannot be read."""
    try:
        if not path or not os.path.isfile(path) or os.path.getsize(path) > MAX_TRANSCRIPT:
            return None
        calls, items, cwd, handback, text = {}, [], '', '', ''
        with open(path, encoding='utf-8', errors='replace') as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                    message = entry.get('message') or {}
                    blocks = message.get('content') if isinstance(message.get('content'), list) else []
                except (ValueError, AttributeError, RecursionError):
                    continue
                cwd = entry.get('cwd') if isinstance(entry.get('cwd'), str) and entry.get('cwd') else cwd
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    ident = block.get('id') if block.get('type') == 'tool_use' else block.get('tool_use_id')
                    ident = ident if isinstance(ident, str) else None          # a malformed id is skipped, never hashed
                    if block.get('type') == 'tool_use' and ident:
                        calls[ident] = (str(block.get('name') or ''), block.get('input'), cwd)
                        given = block.get('input') if isinstance(block.get('input'), dict) else {}
                        if block.get('name') == 'SubagentHandback' and isinstance(given.get('message'), str):
                            handback = given['message']
                    elif block.get('type') == 'tool_result' and ident in calls:
                        tool, given, at = calls.pop(ident)
                        for item in [] if block.get('is_error') else new_items(tool, given, block.get('content'), at):
                            items = [one for one in items if one[:2] != item[:2]] + [item]   # again: moves to the end
                    elif block.get('type') == 'text' and entry.get('type') == 'assistant' and isinstance(block.get('text'), str):
                        text = block['text']
        return items, handback or text          # the report handed back wins over the agent's last words
    except OSError:
        return None


def git(folder, deadline, *args, stdin=None):
    """git's output in `folder`, or None when it cannot be asked (no folder, no git, out of time, an error exit). It takes
    no optional lock, so an agent committing in the same folder is never stopped by it."""
    left = min(GIT_SECONDS, deadline - time.monotonic())
    if left <= 0 or not folder or not os.path.isdir(folder):
        return None
    try:
        done = subprocess.run(['git', '--no-optional-locks', '-C', folder] + list(args), input=stdin, capture_output=True,
                              text=True, timeout=left)
        return done.stdout if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def edit_mark(path, deadline):
    """What git says now about a file the agent edited, asked in the file's own folder so it reaches its own repository."""
    folder, name = os.path.split(path)
    status = git(folder, deadline, 'status', '--porcelain', '-z', '--untracked-files=all', '--ignored=matching', '--', name)
    if status is None:
        return UNCHECKED
    codes = [one[:2] for one in status.split('\0') if len(one) > 3]
    return IGNORED if codes and all(code == '!!' for code in codes) else UNCOMMITTED if codes else ''


def known_commits(shas, folders, deadline):
    """The shas that some folder's repository has as commits: one `cat-file --batch-check` per folder for those still unknown."""
    left = sorted(set(shas))
    for folder in folders:
        if not left:
            break
        out = git(folder, deadline, 'cat-file', '--batch-check', stdin=''.join('%s^{commit}\n' % sha for sha in left))
        if out is not None:
            answers = out.splitlines()
            # `<sha> commit <size>` is a commit; `missing` or `ambiguous` is not one this repository can name.
            left = [sha for at, sha in enumerate(left) if at >= len(answers) or answers[at].split(' ')[1:2] != ['commit']]
    return set(shas) - set(left)


def marked(items):
    """The kept items' shown texts with what git says now, within GIT_BUDGET seconds in all."""
    deadline = time.monotonic() + GIT_BUDGET
    edits = {key: edit_mark(key, deadline) for kind, key, _, _ in items if kind == 'edit'}
    folders = list(dict.fromkeys([folder for kind, _, _, folder in items if kind == 'commit'] +
                                 [os.path.dirname(key) for key in edits]))
    known = known_commits([key for kind, key, _, _ in items if kind == 'commit' and key], folders, deadline)
    return [shown + (edits[key] if kind == 'edit' else '' if key in known else UNVERIFIED) for kind, key, shown, _ in items]


def from_transcript(path):
    """The field rebuilt at the stop from the agent's transcript, or None when it cannot be read (the live list stays)."""
    found = read_transcript(path)
    if found is None:
        return None
    items, report = found
    if not items:
        return first_line(report)
    return joined(marked(items[-MAX_ENTRIES:]), dropped=max(0, len(items) - MAX_ENTRIES))
