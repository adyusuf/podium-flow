"""Layer 3 of the Status box (user decision 16/11/2026; order: state, then agent, then the agent's own work): the work
list under a subagent's row, kept in the row's `work` field.

    edited <path>             a file the agent changed with Edit/Write/NotebookEdit and the harness ran without error;
                              `(uncommitted)` at the stop when `git status` in the agent's folder still shows it
    commit <sha> <subject>    a commit the agent's git command printed; `(not verified)` at the stop when the sha is not
                              a commit in the agent's folder (or git cannot be asked)
    reported, not verified: <first line of its report>
                              only for an agent that edited and committed nothing (a review): its own words, never a
                              measurement

Live, each tool call of the agent adds what its payload shows (`add_live`); at the stop the list is rebuilt from the
agent's transcript, which holds every run (`from_transcript`). The newest MAX_ENTRIES are kept, with `… N earlier`
first when more were seen. The field is one line of at most MAX_WORK characters (the row's clip on load uses that cap
for `work`, MAX_TEXT for the rest): entries are joined by SEPARATOR, each at most ENTRY characters with its mark (a path
keeps its end).
"""
import json
import os
import re
import subprocess

from podium_status_rows import MAX_WORK, clip

SEPARATOR = '\u241e'          # a printable character (the record-separator sign), so the row's clip keeps it
MAX_ENTRIES = 5
ENTRY = MAX_WORK // (MAX_ENTRIES + 1) - 1     # every entry, the `… N earlier` one and the separators fit MAX_WORK
EDIT_TOOLS = ('Edit', 'Write', 'MultiEdit', 'NotebookEdit')
# What `git commit` prints first: `[branch 1a2b3c4] subject`, `[main (root-commit) 1a2b3c4] subject`.
COMMIT = re.compile(r'^\[[^\]\s]+(?: \([\w -]+\))? ([0-9a-f]{7,40})\] (.+)$', re.M)
EARLIER = re.compile(r'^… (?:\d+ )?earlier$')
REPORTED = 'reported, not verified: '
UNCOMMITTED, UNVERIFIED = ' (uncommitted)', ' (not verified)'
MAX_TRANSCRIPT = 64 * 1024 * 1024
GIT_SECONDS = 3


def parse(text):
    """(the `… earlier` entry or '', the entries kept) from a stored `work` field."""
    items = [one for one in str(text or '').split(SEPARATOR) if one.strip()]
    return (items[0], items[1:]) if items and EARLIER.match(items[0]) else ('', items)


def joined(items, marker='', live=False):
    """The stored field: the newest MAX_ENTRIES of `items` (all distinct), `… N earlier` first when some were dropped. A
    live list cannot count what it dropped (a file dropped and edited again would count twice), so it keeps
    `… earlier` with no number; the stop counts from the whole transcript."""
    dropped = len(items) - MAX_ENTRIES
    marker = ('… earlier' if live else '… %d earlier' % dropped) if dropped > 0 else marker
    return SEPARATOR.join(([marker] if marker else []) + items[-MAX_ENTRIES:])


def shown_path(path, cwd):
    """A path relative to the agent's folder when it is inside it, `~/...` under the home folder; a long one keeps its end."""
    path, cwd = str(path), str(cwd or '')
    if cwd and path.startswith(cwd.rstrip('/') + '/'):
        path = path[len(cwd.rstrip('/')) + 1:]
    elif path.startswith(os.path.expanduser('~') + '/'):
        path = '~' + path[len(os.path.expanduser('~')):]
    path = clip(path)
    room = ENTRY - len('edited ') - len(UNCOMMITTED)        # room for the mark the stop may add
    return path if len(path) <= room else '…' + path[-(room - 1):]


def edited(path, cwd):
    return 'edited ' + shown_path(path, cwd)


def committed(sha, subject):
    return clip('commit %s %s' % (sha[:7], subject))[:ENTRY - len(UNVERIFIED)]


def add(text, entry):
    """The field with `entry` appended; an equal entry already there moves to the end instead of showing twice."""
    marker, items = parse(text)
    return joined([one for one in items if one != entry] + [entry], marker, live=True)


def result_text(value):
    """The text of a tool result: a string, the `stdout` of a Bash result, or the text blocks of a list."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get('stdout') or '') + '\n' + str(value.get('content') if isinstance(value.get('content'), str) else '')
    if isinstance(value, list):
        return '\n'.join(str(block.get('text') or '') for block in value if isinstance(block, dict))
    return ''


def is_git(command):
    return isinstance(command, str) and re.search(r'\bgit\b', command) is not None


def new_entries(tool, given, result, cwd):
    """What one tool call adds to the list: an edited file, or the commits a git command printed."""
    given = given if isinstance(given, dict) else {}
    if tool in EDIT_TOOLS:
        path = given.get('file_path') or given.get('notebook_path')
        return [edited(path, cwd)] if isinstance(path, str) and path else []
    if tool == 'Bash' and is_git(given.get('command')):
        return [committed(sha, subject) for sha, subject in COMMIT.findall(result_text(result))]
    return []


def add_live(text, payload):
    """The field after one PostToolUse of the agent, from what its payload shows."""
    if payload.get('tool_response', {}).get('is_error') if isinstance(payload.get('tool_response'), dict) else False:
        return text or ''
    for entry in new_entries(str(payload.get('tool_name') or ''), payload.get('tool_input'), payload.get('tool_response'),
                             payload.get('cwd')):
        text = add(text, entry)
    return text or ''


def first_line(report):
    """The first line of a report that says something: no heading marks, emphasis or code ticks."""
    for line in str(report or '').splitlines():
        if line.lstrip().startswith('#'):          # a heading names the report; the first sentence says what it found
            continue
        line = re.sub(r'[*`_#>]+', '', line).strip(' -:|')
        if line and not re.match(r'^-{3,}$', line):
            return clip(REPORTED + line)[:ENTRY]
    return ''


def read_transcript(path):
    """(entries in order, the agent's last folder, its last report) from its transcript; None when it cannot be read."""
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
                cwd = str(entry.get('cwd') or cwd)
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    if block.get('type') == 'tool_use':
                        calls[block.get('id')] = (str(block.get('name') or ''), block.get('input'))
                        given = block.get('input') if isinstance(block.get('input'), dict) else {}
                        if block.get('name') == 'SubagentHandback' and isinstance(given.get('message'), str):
                            handback = given['message']
                    elif block.get('type') == 'tool_result' and not block.get('is_error') and block.get('tool_use_id') in calls:
                        tool, given = calls.pop(block['tool_use_id'])
                        items += [one for one in new_entries(tool, given, block.get('content'), cwd) if one not in items]
                    elif block.get('type') == 'text' and entry.get('type') == 'assistant' and block.get('text'):
                        text = block['text']
        return items, cwd, handback or text          # the report handed back wins over the agent's last words
    except OSError:
        return None


def git(cwd, *args):
    """git's output in `cwd`, or None when it cannot be asked (no folder, no git, a timeout, an error exit)."""
    try:
        done = subprocess.run(['git', '-C', cwd] + list(args), capture_output=True, text=True, timeout=GIT_SECONDS)
        return done.stdout if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def verified(items, cwd):
    """The entries with what git says now: an edited file still uncommitted, a commit git does not know."""
    usable = bool(cwd) and os.path.isdir(cwd)
    paths = [one[len('edited '):] for one in items if one.startswith('edited ') and not one.startswith('edited …')]
    # `--short` prints paths relative to the folder git runs in, as the entries hold them (`--porcelain` would not).
    dirty = git(cwd, 'status', '--short', '--untracked-files=all', '--', *paths) if usable and paths else None
    changed = {line[3:].split(' -> ')[-1].strip() for line in (dirty or '').splitlines()}
    out = []
    for one in items:
        if one.startswith('edited ') and one[len('edited '):] in changed:
            one += UNCOMMITTED
        elif one.startswith('commit '):
            sha = one.split(' ')[1]
            if not usable or git(cwd, 'cat-file', '-e', sha + '^{commit}') is None:
                one += UNVERIFIED
        out.append(one)
    return out


def from_transcript(path):
    """The field rebuilt at the stop from the agent's transcript, or None when it cannot be read (the live list stays)."""
    found = read_transcript(path)
    if found is None:
        return None
    items, cwd, report = found
    if not items:
        return first_line(report)
    return joined(verified(items, cwd))
