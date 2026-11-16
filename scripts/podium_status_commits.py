"""Which commits a Bash call made, read from its command and its output - layer 3 of the Status box (podium_status_work.py,
which re-exports these names). Split out of it on 17/11/2026 to keep both files under 300 lines (#9).

Only a `git commit` where a command starts counts, read after one left-to-right scan has taken out heredoc bodies, quoted
strings and `#` comments (a `#` that starts a word outside quotes, so `don't` inside a comment opens no quote) and kept a
backslash-escaped character as a plain one; `git commit --dry-run` makes nothing and does not count. The sha comes from
git's `[branch sha] subject` line, or for `git commit -q ... && git log --oneline -1` from the log: its line whose subject
is the commit's own message when that command shows one (`-m`, `--message`, a `"$(cat <<EOF ...)"` body), else - `-F`, a
`$variable` - its first `sha subject` line, which the stop's commit-time check limits to a commit made within that call
(QA pass 3 L1, 16/11/2026; the message is read from the commit's own words only, QA 17/11/2026 F1).
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
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*[\"']?([A-Za-z_]\w*)")
DOUBLE_END = re.compile(r'(?:[^"\\]|\\.)*"', re.S)
DRY_RUN = re.compile(r'(?<!\S)--dry-run(?!\S)')
WORD_BREAK = ' \t\n;&|()<>'
# A double-quoted `$(cat <<TAG ... TAG)` body, the usual way a long commit message is given.
CAT_BODY = re.compile(r'"\$\(cat\s+<<-?\s*([\'"]?)(\w+)\1[^\n]*\n(.*?)\n[ \t]*\2[ \t]*\n\s*\)"', re.S)
SHORT_WITH_VALUE = 'mFCct'                  # git commit's short options that take a value (the rest of the word or the next)
LONG_WITH_VALUE = ('author', 'date', 'cleanup', 'trailer', 'template', 'pathspec-from-file')
MESSAGE_ELSEWHERE = ('file', 'reuse-message', 'reedit-message', 'fixup', 'squash')
DECORATION = re.compile(r'^\((?:[^()]|\([^()]*\))*\) ')      # `(HEAD -> main, tag: v1) ` with log.decorate set


def scan(command):
    """(plain text, origin): heredoc bodies dropped, each quoted string emptied to "", `#` comments dropped and an escaped
    character kept, in one left-to-right pass; origin[i] is the index in `command` of the plain text's i-th character."""
    kept, tag, at = [], None, 0
    for line in command.splitlines(keepends=True):
        start, at = at, at + len(line)
        if tag is not None:
            tag = None if line.strip() == tag else tag
            continue
        kept.append((start, line))
        found = HEREDOC.search(line)
        tag = found.group(1) if found else None
    src = ''.join(line for _, line in kept)
    where = [start + k for start, line in kept for k in range(len(line))]
    chars, origin, i, word_start = [], [], 0, True
    while i < len(src):
        c = src[i]
        if c == '#' and word_start:
            i = src.find('\n', i) if '\n' in src[i:] else len(src)
            continue
        if c in '\'"':
            closed = DOUBLE_END.match(src, i + 1) if c == '"' else None
            end = src.find("'", i + 1) + 1 if c == "'" else closed.end() if closed else 0
            chars.append('""'), origin.extend((where[i], where[i]))
            i, word_start = (end if end > 0 else len(src)), False       # an unclosed quote runs to the end
            continue
        step = 2 if c == '\\' and i + 1 < len(src) else 1
        chars.append(src[i:i + step]), origin.extend(where[i:i + step])
        i, word_start = i + step, c in WORD_BREAK          # an escaped character starts no word
    return ''.join(chars), origin


def plain(command):
    """The command as the shell runs it: heredoc bodies, quoted strings and `#` comments taken out."""
    return scan(command)[0]


def words(text):
    """[(value, known)] of the first simple command in `text`, quotes resolved as bash does; `known` is False where a
    `$` or a backquote would expand, so the value is not what the shell passes."""
    out, i, word, known, started = [], 0, '', True, False
    while i < len(text):
        c = text[i]
        if c in ' \t' or (c in ';&|\n)' or (c == '#' and not started)):
            if started:
                out.append((word, known))
                word, known, started = '', True, False
            if c not in ' \t':
                break
            i += 1
            continue
        if text.startswith('\\\n', i):                  # a line continuation joins, it adds nothing
            i += 2
            continue
        started = True
        body = CAT_BODY.match(text, i) if c == '"' else None
        if body:                                        # a quoted tag keeps `$` literal; an unquoted one expands it
            expands = not body.group(1) and re.search(r'[$`]', body.group(3))
            word, known, i = word + body.group(3), known and not expands, body.end()
        elif c == '\\':
            word, i = word + text[i + 1:i + 2], i + 2
        elif c == "'":
            end = text.find("'", i + 1)
            stop = end if end >= 0 else len(text)
            word, known, i = word + text[i + 1:stop], known and end >= 0, stop + 1
        elif c == '"':
            found = DOUBLE_END.match(text, i + 1)
            inner = text[i + 1:found.end() - 1] if found else text[i + 1:]
            known = known and found is not None and not re.search(r'(?<!\\)[$`]', inner)
            word += re.sub(r'\\([\\"$`])|\\\n', lambda m: m.group(1) or '', inner)
            i = found.end() if found else len(text)
        else:
            word, known, i = word + c, known and c not in '$`', i + 1
    if started:
        out.append((word, known))
    return out


def subject(command):
    """The subject git gives the message the commit command shows - its first paragraph, lines joined by a space - or None
    when it shows none it can be sure of (no `-m`, `-F file`, `-C`, a `$variable`). Reads the first simple command from
    its `commit` word on."""
    given = words(command)
    names = [value for value, _ in given]
    if 'commit' not in names:
        return None
    rest, messages = given[names.index('commit') + 1:], []
    while rest:
        (value, known), rest = rest[0], rest[1:]
        if value == '--':
            break
        if value.startswith('--'):
            name, equals, inline = value[2:].partition('=')
            if name in MESSAGE_ELSEWHERE:
                return None
            if name in ('message',) + LONG_WITH_VALUE and not equals:
                (inline, known), rest = (rest[0], rest[1:]) if rest else (('', False), rest)
            if name == 'message':
                messages.append((inline, known))
        elif value.startswith('-') and len(value) > 1:
            for at, letter in enumerate(value[1:], 2):
                if letter in SHORT_WITH_VALUE:
                    if letter in 'FCc':
                        return None
                    taken = (value[at:], known) if value[at:] else rest[0] if rest else ('', False)
                    rest = rest if value[at:] or not rest else rest[1:]
                    messages += [taken] if letter == 'm' else []
                    break
    if not messages or not all(known for _, known in messages):
        return None
    lines = [line.rstrip() for line in '\n\n'.join(value for value, _ in messages).split('\n')]
    while lines and not lines[0]:
        lines.pop(0)
    paragraph = lines[:lines.index('')] if '' in lines else lines
    return ' '.join(paragraph) or None


def same_subject(shown, wanted):
    """A log line's subject is the wanted one, by words, with or without the `(HEAD -> ...)` decoration in front."""
    return any(' '.join(one.split()) == ' '.join(wanted.split()) for one in (shown, DECORATION.sub('', shown)))


def commits_of(command, output):
    """(sha, subject) of each commit a successful `git commit` printed; (None, '') when it printed no sha. A log line counts
    only when `git log` runs after the commit (`&&`, `;` or a new line between, never `||`, a pipe or `&`); if the commit
    failed, that line is the older HEAD, and the stop's commit-time check marks it `(not verified)`."""
    text, origin = scan(command) if isinstance(command, str) else ('', [])
    commit = next((one for one in re.finditer(GIT_VERB % 'commit', text)
                   if not DRY_RUN.search(re.split(r'[;&|\n)]', text[one.end():], maxsplit=1)[0])), None)
    if commit is None:
        return []
    found = COMMIT.findall(output)
    rest = text[commit.end():]
    log = re.search(GIT_VERB % 'log', rest)
    # The text up to `git log`, with the separator its match starts on: `&&`, `;` and new lines run it after the commit.
    if not found and log and not re.search(r'[|&]', rest[:log.start() + 1].replace('&&', '')):
        wanted = subject(command[origin[commit.end() - len('commit')]:])      # the commit's own words, from `commit` on
        lines = ONELINE.findall(output)
        found = [(sha, DECORATION.sub('', shown)) for sha, shown in lines
                 if wanted is None or same_subject(shown, wanted)][:1]
    return found or [(None, '')]
