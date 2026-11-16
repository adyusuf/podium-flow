"""Which commits a Bash call made, read from its command and its output - layer 3 of the Status box (podium_status_work.py,
which re-exports these names). Split out of it on 17/11/2026 to keep both files under 300 lines (#9).

Only a `git commit` where a command starts counts, read after heredoc bodies, quoted strings and `#` comments are taken out
and a backslash-escaped character is kept as a plain one (so `don\\'t` opens no quote); `git commit --dry-run` makes
nothing and does not count. The sha comes from git's `[branch sha] subject` line, or for `git commit -q ... && git log
--oneline -1` from the log: its line whose subject is the commit's message when the command shows that message (`-m`,
`--message`, a `$(cat <<EOF ...)` body), else its first `sha subject` line (QA pass 3 L1, 16/11/2026: the first line is not
necessarily the log's own; the stop's commit-time check still limits it to a commit made within that call).
"""
import re

# `git commit`'s first line: `[branch 1a2b3c4] subject`, `[main (root-commit) 1a2b3c4] s`, `[detached HEAD 1a2b3c4] s`.
COMMIT = re.compile(r'^\[[^\]\n]+ ([0-9a-f]{7,40})\] (.+)$', re.M)
ONELINE = re.compile(r'^([0-9a-f]{7,40}) (.+)$', re.M)
# `git <verb>` where a command starts (as podium_status_hooks.COMMIT, on text with quotes and heredocs taken out): the
# start, after ; & | a newline ( ` { ! or then/do/else/elif, behind env/command/sudo/exec/time/nohup/xargs or VAR=value,
# git by a path, with its global options (`-C dir`, `-c k=v`, `--no-pager`).
GIT_VERB = (r'(?:^|[;&|\n(`{!]|\b(?:then|do|else|elif)\s)\s*(?:(?:env|command|sudo|exec|time|nohup|xargs)(?:\s+-\S+)*\s+'
            r'|\w+=\S*\s+)*(?:[\w.~-]*/)*git(?:\s+-[Cc]\s+\S+|\s+-\S+)*\s+%s(?![-\w])')
# A shell word that is quoted, or one escaped character outside quotes (kept: it opens no quote).
QUOTED = re.compile(r'\\.|"(?:[^"\\]|\\.)*"|\'[^\']*\'', re.S)
COMMENT = re.compile(r'(?:^|(?<=\s))#[^\n]*', re.M)
DRY_RUN = re.compile(r'(?<!\S)--dry-run(?!\S)')
GIT_COMMIT_AT = re.compile(r'(?<![-\w])git\b[^\n;&|]*?\scommit(?![-\w])')
# The first message a commit command gives: `-m`/`-am`/`--message` with a `$(cat <<TAG` body, a quoted or a bare word.
MESSAGE = re.compile(r'(?<!\S)(?:-[a-zA-Z]*m|--message)(?:=|\s*)(?:"\$\(cat\s+<<-?\s*[\'"]?(\w+)[\'"]?[^\n]*\n(.*?)\n\s*\1\s*\n'
                     r'|"((?:[^"\\]|\\.)*)"|\'([^\']*)\'|([^\s;&|\'"()]+))', re.S)


def plain(command):
    """The command with heredoc bodies dropped, every quoted string emptied and `#` comments dropped: what is left is what
    the shell runs."""
    kept, tag = [], None
    for line in command.splitlines():
        if tag is not None:
            tag = None if line.strip() == tag else tag
            continue
        kept.append(line)
        found = re.search(r"(?<!<)<<(?!<)-?\s*[\"']?([A-Za-z_]\w*)", line)
        tag = found.group(1) if found else None
    text = QUOTED.sub(lambda m: m.group(0) if m.group(0).startswith('\\') else '""', '\n'.join(kept))
    return COMMENT.sub('', text)


def subject(command):
    """The subject git gives the first message the command shows - its first paragraph on one line - or None when the
    command shows none it can be sure of (no `-m`, `-F file`, a `$variable`)."""
    found = MESSAGE.search(command)
    if found is None:
        return None
    body = found.group(2) if found.group(1) else next(one for one in found.groups()[2:] if one is not None)
    if found.group(3) is not None:
        body = re.sub(r'\\(.)', r'\1', body)
    if found.group(4) is None and ('$' in body or '`' in body):
        return None
    paragraph = body.strip().split('\n\n')[0]
    return ' '.join(line.strip() for line in paragraph.splitlines() if line.strip()) or None


def commits_of(command, output):
    """(sha, subject) of each commit a successful `git commit` printed; (None, '') when it printed no sha. A log line counts
    only when `git log` runs after the commit (`&&`, `;` or a new line between, never `||`, a pipe or `&`); if the commit
    failed, that line is the older HEAD, and the stop's commit-time check marks it `(not verified)`."""
    text = plain(command) if isinstance(command, str) else ''
    commit = next((one for one in re.finditer(GIT_VERB % 'commit', text)
                   if not DRY_RUN.search(re.split(r'[;&|\n)]', text[one.end():], maxsplit=1)[0])), None)
    if commit is None:
        return []
    found = COMMIT.findall(output)
    rest = text[commit.end():]
    log = re.search(GIT_VERB % 'log', rest)
    # The text up to `git log`, with the separator its match starts on: `&&`, `;` and new lines run it after the commit.
    if not found and log and not re.search(r'[|&]', rest[:log.start() + 1].replace('&&', '')):
        start = GIT_COMMIT_AT.search(command)            # the message is read from the commit on, not an earlier `-m`
        lines, wanted = ONELINE.findall(output), subject(command[start.start():]) if start else None
        found = [next((one for one in lines if wanted is None or one[1].strip() == wanted), None)]
        found = [one for one in found if one]
    return found or [(None, '')]
