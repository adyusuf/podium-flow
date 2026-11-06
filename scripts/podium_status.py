#!/usr/bin/env python3
"""This session's status table, which the pane's Status box shows (user decision 01/11/2026).

The table is the one `standards/00-working-method.md` §10 asks for in a reply during a long run: the item, its state, the
measured figure with the signal it was read from, what it waits on; plus what runs now and what runs next. Claude writes
it at each step, and a background run (a gate, a promotion) may write its own steps; the box re-reads the file after every
tool call and when its modification time changes. Every figure is MEASURED: the script stores what it is given and
invents nothing.

The file is `<session id>.json` in PODIUM_STATUS_DIR (an absolute path; default `~/.claude/podium-status`). Writers take
a lock around read-modify-write, so Claude and a background run never lose each other's rows. Status files nobody has
written to for KEEP_DAYS are removed whenever one is written; a file that is not a status table is never touched.

Usage:
    podium_status.py --session ID now TEXT                  what runs now ('' clears it)
    podium_status.py --session ID next TEXT                 what runs next ('' clears it)
    podium_status.py --session ID row ITEM STATE FIGURE WAITING
                                                             add the row named ITEM, or replace it in place
    podium_status.py --session ID step ITEM STATE PERCENT [--blocker TEXT] [--agent NAME] [--after ITEM] [--note TEXT]
                                                             a step (02/11/2026): its state (STATES), how much is done
                                                             (0-100), what blocks it, who runs it (a subagent; none =
                                                             this session); --after puts a new step after that one,
                                                             else it goes last. Replaced in place.
    podium_status.py --session ID drop ITEM [--agent NAME]  remove the step named ITEM (a unique prefix of the name does too)
    podium_status.py --session ID rename OLD NEW [--agent NAME]
                                                             give a step a new name, in place (OLD may be a unique prefix)
    podium_status.py --session ID clear                     empty the table (also replaces a corrupt file)
    podium_status.py --session ID show [--json]             print it
    podium_status.py hook EVENT                             the plugin's hooks (stdin: the hook payload), in
                                                             podium_status_hooks.py
Exit codes: 0 done, 2 refused (an unusable session id or folder, an unreadable file, a failed write).
"""
import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
import time

try:
    import fcntl
except ImportError:  # Windows: no advisory lock; one writer at a time is then the caller's duty (documented in §10d).
    fcntl = None

# The rows and what is done to them live in podium_status_rows.py (beside this file); the names are re-exported here.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from podium_status_rows import (CLOSED, CONTROL, FIELDS, MAX_ROWS, MAX_TEXT, OPEN, STATES, STEP_FIELDS,  # noqa: E402,F401
                                StatusError, clip, drop_row, percent, put_row, rename_row, running_item, same,
                                step_percent, trim)

KEEP_DAYS = 14
MAX_ID = 100
EMPTY = {'now': '', 'next': '', 'rows': [], 'updated': '', 'budget': ''}
SESSION_ID = re.compile(r'^[A-Za-z0-9_-]{1,%d}$' % MAX_ID)
STATUS_NAME = re.compile(r'^[A-Za-z0-9_-]{1,%d}\.json$' % MAX_ID)


def status_dir():
    chosen = os.environ.get('PODIUM_STATUS_DIR') or os.environ.get('ADYUSUF_STATUS_DIR')     # the older name still read
    if chosen and not os.path.isabs(chosen):
        raise StatusError('PODIUM_STATUS_DIR must be an absolute path (the pane reads it from another directory): %r' % chosen)
    return chosen or os.path.join(os.path.expanduser('~'), '.claude', 'podium-status')


def valid(session):
    """A session id becomes a file name, so it may hold only ASCII letters, digits, '-' and '_'."""
    return isinstance(session, str) and SESSION_ID.match(session) is not None


def status_file(session):
    if not valid(session):
        raise StatusError('not a usable session id: %r' % (session,))
    return os.path.join(status_dir(), session + '.json')


def is_table(data):
    return isinstance(data, dict) and isinstance(data.get('rows', []), list)


def normalise(data):
    """Keep only what a status table holds: string fields, rows that are objects, at most MAX_ROWS of them."""
    rows = [dict({key: clip(row.get(key)) for key in FIELDS + STEP_FIELDS}, percent=step_percent(row))
            for row in data.get('rows', []) if isinstance(row, dict)]
    return {'now': clip(data.get('now')), 'next': clip(data.get('next')), 'rows': trim(rows),
            'updated': clip(data.get('updated')), 'budget': clip(data.get('budget'))}


def load(session):
    path = status_file(session)
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return dict(EMPTY, rows=[])
    except (OSError, ValueError) as error:
        raise StatusError('%s: unreadable (%s); `clear` replaces it' % (path, error))
    if not is_table(data):
        raise StatusError('%s: not a status table; `clear` replaces it' % path)
    return normalise(data)


@contextlib.contextmanager
def locked(session):
    """Holds an exclusive lock on `<session>.lock` for one read-modify-write, so concurrent writers keep each other's rows."""
    path = status_file(session)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if fcntl is None:
        yield
        return
    with open(path[:-len('.json')] + '.lock', 'a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def save(session, data, now=None):
    """Write atomically (a temporary file renamed over the old one), so the box never reads half a file."""
    path = status_file(session)
    data = dict(normalise(data), updated=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() if now is None else now)))
    fd, temp = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.status-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        os.replace(temp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(temp)
        raise
    prune()
    return data


def prune(now=None, keep_days=KEEP_DAYS):
    """Remove status files (and their locks) nobody has written to for `keep_days`. Never raises.

    Only a file named like a session's and holding a status table goes: the folder may be one the user chose
    (PODIUM_STATUS_DIR), where other JSON files must survive.
    """
    limit = (time.time() if now is None else now) - keep_days * 86400
    try:
        folder = status_dir()
        names = os.listdir(folder)
    except (OSError, StatusError):
        return 0
    removed = 0
    for name in names:
        path = os.path.join(folder, name)
        try:
            if not STATUS_NAME.match(name) or os.path.getmtime(path) >= limit:
                continue
            with open(path, encoding='utf-8') as handle:
                data = json.load(handle)
            if not (is_table(data) and 'updated' in data):
                continue
            os.remove(path)
            with contextlib.suppress(OSError):
                os.remove(path[:-len('.json')] + '.lock')
            removed += 1
        except (OSError, ValueError):
            continue
    return removed


def render(data):
    lines = ['budget: ' + data['budget']] if data.get('budget') else []
    if data['now']:
        lines.append('now:  ' + data['now'])
    if data['next']:
        lines.append('next: ' + data['next'])
    for row in data['rows']:
        if row.get('percent') or row.get('agent') or row.get('blocker'):
            done = row['percent'] + '%' if row['percent'] else ''
            lines.append(' | '.join([row['agent'] or 'session', row['item'], row['state'], done, row['blocker'], row['note']]).rstrip(' |'))
        else:
            lines.append(' | '.join(row.get(key, '') for key in FIELDS))
    return '\n'.join(lines) if len(lines) > (1 if data.get('budget') else 0) else '\n'.join(lines + ['nothing running'])


def change(args):
    """One write under the lock. `clear` does not read the old file, so it also replaces a corrupt one."""
    with locked(args.session):
        data = dict(EMPTY, rows=[]) if args.action == 'clear' else load(args.session)
        if args.action in ('now', 'next'):
            data = dict(data, **{args.action: clip(args.text)})
        elif args.action == 'row':
            data = put_row(data, args.item, args.state, args.figure, args.waiting)
        elif args.action == 'step':
            step = {'percent': percent(args.percent), 'blocker': clip(args.blocker), 'agent': clip(args.agent), 'note': clip(args.note)}
            # The older fields carry the % and the blocker too, so an older writer's rewrite keeps them (rule #4).
            figure = step['percent'] + '%' if step['percent'] else ''
            data = put_row(data, args.item, args.state, figure, step['blocker'], step, args.after)
        elif args.action == 'drop':
            data = drop_row(data, args.item, args.agent)
        elif args.action == 'rename':
            data = rename_row(data, args.old, args.new, args.agent)
        if args.action in ('step', 'drop', 'rename') and running_item(data):
            data = dict(data, now=clip(running_item(data)))      # `now` is the name of the step at work, never a raw message
        save(args.session, data)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['hook']:
        try:      # bytes, decoded here: a hook must not fail on the platform's encoding, a closed stdin or a terminal
            raw = b'' if sys.stdin is None or sys.stdin.isatty() else sys.stdin.buffer.read()
        except (OSError, ValueError, AttributeError):
            raw = b''
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import podium_status_hooks as hooks      # beside this file; loaded only for a hook
        return hooks.hook(argv[1] if len(argv) > 1 else '', raw.decode('utf-8', errors='replace'))
    parser = argparse.ArgumentParser(description='This session\'s status table for the pane\'s Status box.')
    parser.add_argument('--session', required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('now', 'next'):
        sub.add_parser(name).add_argument('text')
    row = sub.add_parser('row')
    for name in FIELDS:
        row.add_argument(name)
    step = sub.add_parser('step')
    for name in ('item', 'state', 'percent'):
        step.add_argument(name)
    for name in ('--blocker', '--agent', '--after', '--note'):
        step.add_argument(name, default='' if name != '--after' else None)
    drop = sub.add_parser('drop')
    drop.add_argument('item')
    drop.add_argument('--agent', default='')
    rename = sub.add_parser('rename')
    for name in ('old', 'new'):
        rename.add_argument(name)
    rename.add_argument('--agent', default='')
    sub.add_parser('clear')
    sub.add_parser('show').add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'show':
            data = load(args.session)
            print(json.dumps(data, ensure_ascii=False) if args.json else render(data))
        else:
            change(args)
    except (StatusError, OSError) as error:
        print('podium_status: %s' % error, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
