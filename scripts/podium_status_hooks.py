"""The plugin's hooks on the Status box (user decisions 02/11/2026), split out of podium_status.py so no file passes 300
lines (rule #9). `podium_status.py hook EVENT` reads the hook payload on stdin and calls `hook` here.

    session     a session starts: `now` is "waiting for you"
    prompt      the user's message: `now` is the step at work (else "analysing the request", never the raw message), and
                Claude is reminded to analyse it into steps first
    stop        a turn's end: "waiting for you", or "waiting for background work" while a task or cron runs
    subagent    a subagent starts: its row opens in the box (podium_status_agents.py); the agent writes none itself
    subagent-stop   a subagent ends: its row is done or failed, with its duration, tool calls and output tokens
    tool        a tool call returned: a subagent's row counts it (a call of this session itself changes nothing)
    guard       before an edit or a commit: with `steps.enforce` set to block, refused until the box holds steps

A hook never fails a session: a bad payload or an unusable id does nothing. Only `guard` may refuse (exit code 2), and
under `block` it fails closed: a payload it cannot judge is refused (F-005); a payload with no session id is not a
session's call and runs.
"""
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from podium_status import EMPTY, OPEN, StatusError, clip, load, locked, save, valid  # noqa: E402
from podium_status_agents import agent_name, hooked, start, stop, tick  # noqa: E402
from podium_status_rows import running_item  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'podium_status.py')
# What `now` says when a session starts or a turn ends: it waits for the user, or for its own background work.
WAITING = 'waiting for you'
WAITING_BACKGROUND = 'waiting for background work'
ANALYSING = 'analysing the request'        # a user's message has come in and its steps are not written yet
# The turns a person starts: a system-started turn (a task notification, a wake-up) must not replace the user's task.
USER_SOURCES = (None, 'user', 'sdk')
# Where an edit is Claude's own bookkeeping, never code work (standards/13 §8a): its notes and plans, the podium settings
# and status files, a project's mode files, temp files. Code under ~/.claude (a mod, a plugin) is code work. Folders are
# compared by whole path components: `~/.claude/plans-x/` is not `~/.claude/plans/` (F-003).
CLAUDE_HOME = os.path.join(os.path.expanduser('~'), '.claude')
BOOKKEEPING = tuple(os.path.normcase(os.path.join(CLAUDE_HOME, name)) for name in (
    'projects', 'plans', 'todos', 'podium-status', 'podium-session', 'podium-seen'))
# Temp folders hold scratch files, bookkeeping too - but not a file of a git work tree checked out there (F-003).
TEMP_ROOTS = tuple(os.path.normcase(path) for path in {os.path.realpath(tempfile.gettempdir()), '/tmp', '/private/tmp',
                                                        '/var/folders', '/private/var/folders'})
# <any>/.claude/<name>: a project's mode and settings files, and the user's own ~/.claude/podium.json (adyusuf.json before).
PROJECT_BOOKKEEPING = ('mode', 'mode-model', 'podium.json', 'adyusuf.json')
# `git commit` where a command starts: the line's start, after ;, &, |, a newline, `(`, `$(`, a backtick, or `then`, `do`,
# `else`, `elif`; behind `env [VAR=…]`, `command` or a VAR=value; git options such as -C <dir> or -c k=v allowed (F-004).
# Bash file writes (sed -i, >, tee) are left out on purpose: the guard holds Edit/Write/NotebookEdit and commits, and a
# test pins that scope.
COMMIT = re.compile(r'(?:^|[;&|\n(`]|\b(?:then|do|else|elif)\s)\s*'
                    r'(?:(?:env|command)(?:\s+-\S+)*\s+|\w+=\S*\s+)*'
                    r'git(?:\s+(?:-[Cc]\s+\S+|--(?:git-dir|work-tree|namespace)\s+\S+|-\S+))*\s+commit(?![-\w])')


def hook_text(event, payload, data=None):
    """What `now` becomes for one hook payload, or None to leave the table alone. A user's message is never echoed: `now`
    is the name of the step at work in `data`, or "analysing the request" while there is none (user decision 05/11/2026)."""
    if event == 'prompt':
        if payload.get('source') not in USER_SOURCES:
            return None
        return running_item(data or EMPTY) or ANALYSING
    if event == 'stop':
        return WAITING_BACKGROUND if payload.get('background_tasks') or payload.get('session_crons') else WAITING
    return WAITING if event == 'session' else None


def enforce(session):
    """The `steps.enforce` setting this session runs on: 'block' or 'remind' (block when it cannot be read)."""
    try:
        import podium_layers
        value = podium_layers.load(session=session)[0].get('steps.enforce', ('block', ''))[0]
    except Exception:  # noqa: BLE001 - a hook falls back to the shipped default, never fails
        return 'block'
    return value if value in ('block', 'remind') else 'block'


def open_steps(session, agents):
    """Whether one of `agents` ('' = this session) has a step still to finish, written with `step` (it has a %) or by the
    hooks (a subagent's own row): a plan left from a finished task does not let the next task's edits through (qa,
    02/11/2026). None: the file is unreadable."""
    try:
        rows = load(session)['rows']
    except (StatusError, OSError):
        return None
    return any(row.get('agent', '') in agents and (row.get('percent') != '' or hooked(row)) and row.get('state') in OPEN
               for row in rows)


def under(path, folder):
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def in_work_tree(path, root):
    """Whether a folder from `path`'s own up to `root` holds `.git` (a folder, or a worktree's file)."""
    folder = os.path.dirname(path)
    while under(folder, root):
        if os.path.exists(os.path.join(folder, '.git')):
            return True
        if os.path.dirname(folder) == folder:
            break
        folder = os.path.dirname(folder)
    return False


def bookkeeping(path):
    path = os.path.normcase(path)
    parent, name = os.path.split(path)
    if any(under(path, folder) for folder in BOOKKEEPING):
        return True
    if os.path.basename(parent) == '.claude' and name in PROJECT_BOOKKEEPING:
        return True
    return any(under(path, root) and not in_work_tree(path, root) for root in TEMP_ROOTS)


def reminder(session):
    """What every user message carries: analyse first, steps in the box, % and blockers kept current."""
    return ('podium steps (setting steps.enforce: %s): before acting on this message, analyse it. If it adds work, '
            'write its steps into the Status box first, in order, as phases where it helps: python3 "%s" --session %s '
            'step "<n. short name>" "not started" 0 [--after "<step>"] [--note "<details>"] (a request that arrives '
            'mid-work goes in with --after; keep the name short, details go in --note). Keep each step current: state '
            'running/done/blocked/did not run, its %% done, --blocker "<what>" when stuck. '
            'Status box: standards/00 §1a, §10d.' % (enforce(session), SCRIPT, session))


def subagent_note(name):
    return ('podium steps: you are "%s". Your row in the parent\'s Status box is written and closed by the hooks, with its '
            'time, tool calls and output tokens: do not write it, and do not write a %% for it.' % name)


def blocked(payload):
    """Why an edit or a commit is refused, or '' to let it run: with `block`, code work waits for the steps. Raises
    TypeError on a payload or `tool_input` that is not an object; `guard` turns that into a refusal under `block`."""
    if not isinstance(payload, dict):
        raise TypeError('the payload is not an object')
    session = str(payload.get('session_id') or '')
    tool, given = str(payload.get('tool_name') or ''), payload.get('tool_input', {})
    if not isinstance(given, dict):
        raise TypeError('tool_input is not an object')
    if tool == 'Bash':
        work = bool(COMMIT.search(str(given.get('command') or '')))
    else:
        given_path = str(given.get('file_path') or given.get('notebook_path') or '')
        work = given_path != '' and not bookkeeping(os.path.abspath(given_path))
    if not work or not valid(session):     # no id: not a session's call (Claude Code always sends one), let it run
        return ''
    # A subagent may go on under its own row (the hooks open it at SubagentStart) or the session's steps.
    name = agent_name(payload) if payload.get('agent_id') else ''
    found = open_steps(session, {'', name})
    if found or enforce(session) != 'block':
        return ''
    if found is None:
        return ('podium steps: the Status file cannot be read; replace it with python3 "%s" --session %s clear, then write '
                'the steps. Then retry.' % (SCRIPT, session))
    sign = ' --agent "%s"' % name if name else ''
    return ('podium steps (steps.enforce: block): no step of this task is open. Analyse the work and write its steps into '
            'the Status box first: python3 "%s" --session %s step "<n. step>" "not started" 0%s. Then retry.'
            % (SCRIPT, session, sign))


def guard(payload_text):
    """The `guard` hook's exit code. Under `block` it fails CLOSED (F-005): a payload that does not parse, a `tool_input`
    that is not an object, or an error while judging refuses the call (exit 2) with a short reason; under `remind` it
    says so on stderr and lets the call run."""
    session = ''
    try:
        payload = json.loads(payload_text)
        session = str(payload.get('session_id') or '') if isinstance(payload, dict) else ''
        reason = blocked(payload)
    except Exception as error:  # noqa: BLE001 - judged below: a refusal under block, a stderr line under remind
        problem = '%s: %s' % (type(error).__name__, error) if isinstance(error, TypeError) else type(error).__name__
        if enforce(session if valid(session) else None) != 'block':
            print('podium steps: the guard could not judge this call (%s); steps.enforce is remind, so it runs.' % problem,
                  file=sys.stderr)
            return 0
        reason = ('podium steps (steps.enforce: block): the guard could not judge this call (%s), so it is refused. '
                  'Retry the call; if this repeats, report it.' % problem)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


def spend(session, payload):
    """This session's measured spend line (user decision 06/11/2026: shown, never a stop), '' when nothing was measured.
    Read BEFORE the status lock is taken (qa 06/11/2026): parsing a long transcript must not hold up a step's write."""
    try:
        import podium_budget
        return podium_budget.status_line(session, str(payload.get('transcript_path') or ''))
    except Exception:  # noqa: BLE001 - a hook never fails a session over a figure
        return ''


def budget(data, text):
    """The table with `text` in `budget`; an empty one leaves the last figure as it was."""
    return dict(data, budget=clip(text)) if text else data


def context(event, text):
    print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'additionalContext': text}}))


def write(session, change):
    """One read-modify-write of the session's table under the lock; `change(data)` returns the new table. A corrupt file
    is replaced, as `clear` would."""
    with locked(session):
        try:
            data = load(session)
        except StatusError:
            data = dict(EMPTY, rows=[])
        save(session, change(data))


def hook(event, payload_text):
    """Run one hook; returns the exit code (2 only when `guard` refuses). Never raises."""
    if event == 'guard':
        return guard(payload_text)
    try:
        payload = json.loads(payload_text)
        session = str(payload.get('session_id') or '')
        if not valid(session):
            return 0
        if event == 'subagent':
            context('SubagentStart', subagent_note(agent_name(payload)))
            write(session, lambda data: start(data, payload, time.time()))
            return 0
        if event == 'subagent-stop':
            line = spend(session, payload)
            write(session, lambda data: budget(stop(data, payload, time.time()), line))
            return 0
        if event == 'tool':
            if payload.get('agent_id'):          # a call of this session itself needs no write: the hook costs one start-up
                write(session, lambda data: tick(data, payload, time.time()))
            return 0
        if event == 'prompt' and payload.get('source') in USER_SOURCES:
            line = spend(session, payload)
            write(session, lambda data: budget(dict(data, now=clip(hook_text(event, payload, data)), next=''), line))
            context('UserPromptSubmit', reminder(session))
            return 0
        text = hook_text(event, payload)
        if text is not None:
            line = spend(session, payload)
            write(session, lambda data: budget(dict(data, now=clip(text), next=''), line))
    except Exception:  # noqa: BLE001 - a hook never fails a session, whatever the payload or the file holds
        return 0
    return 0
