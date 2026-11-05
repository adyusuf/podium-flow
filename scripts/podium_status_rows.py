"""The rows of a status table and the operations on them, split out of podium_status.py so no file passes 300 lines
(rule #9). Pure functions over `{'now', 'next', 'rows', 'updated'}`: nothing here reads or writes a file.

A row is named by its item and who runs it (`agent`, '' = this session). `drop`, `rename` and `--after` find a step by its
exact name first and then by a prefix of it (user decision 05/11/2026), so a long step name need not be retyped.
"""
import re

MAX_TEXT = 300
MAX_ROWS = 50
FIELDS = ('item', 'state', 'figure', 'waiting')
# A step's own fields: a row written by `row` leaves them empty. `since` (epoch seconds) and `tools` (tool calls so far)
# and `model` (only when the hook payload names it) belong to the row a subagent's hooks write: its time and tool count
# are measured from them.
STEP_FIELDS = ('percent', 'blocker', 'agent', 'note', 'since', 'tools', 'model')
# `failed` (05/11/2026) is a step that ended in error: not open (nothing is left to finish) and not closed (it must stay
# visible until someone looks at it), so `trim` keeps it longer than a finished step.
STATES = ('not started', 'running', 'done', 'blocked', 'did not run', 'failed')
OPEN, CLOSED = STATES[:2] + STATES[3:4], (STATES[2], STATES[4])      # a step still to finish, and one that is over
CONTROL = re.compile('[\x00-\x1f\x7f-\x9f]')


class StatusError(Exception):
    """A refusal the command line reports with exit code 2."""


def clip(text):
    """One line of at most MAX_TEXT characters with no control characters: the box draws one line per field."""
    flat = ' '.join(CONTROL.sub(' ', '' if text is None else str(text)).split())
    return flat if len(flat) <= MAX_TEXT else flat[:MAX_TEXT - 1] + '…'


def percent(value):
    """How much of a step is done, as '0'..'100', or '' when not given (`45`, `45%`, `45.5` read as 45)."""
    match = re.match(r'^\s*(\d+(?:\.\d+)?)\s*%?\s*$', '' if value is None else str(value))
    return str(min(100, int(float(match.group(1))))) if match else ''


def step_percent(row):
    """A row's percentage; an older writer keeps only `figure`, where `step` also writes it (`45%`), so it is read back."""
    given = percent(row.get('percent'))
    return given or (percent(row.get('figure')) if re.match(r'^\d{1,3}%$', str(row.get('figure') or '')) else '')


def trim(rows):
    """At most MAX_ROWS: a finished subagent step goes first, then any other subagent step, then a finished step of this
    session; a step of this session still to finish goes last (qa, 02/11/2026: the plan must not vanish silently)."""
    rows = list(rows)
    picks = (lambda row: row['agent'] and row['state'] in CLOSED, lambda row: row['agent'] and row['state'] != 'failed',
             lambda row: row['agent'], lambda row: row['state'] in CLOSED, lambda row: True)
    while len(rows) > MAX_ROWS:
        rows.pop(next(at for pick in picks for at, row in enumerate(rows) if pick(row)))
    return rows


def same(one, item, agent):
    """A row is named by its item and who runs it: two agents may each have a step of the same name."""
    return one.get('item') == item and one.get('agent', '') == agent


def find(rows, item, agent=None):
    """Indexes of the rows `item` names: the exact name if any row has it, else the rows whose name starts with it.

    `agent` None looks at every runner; '' at this session only; a name at that agent, exact first, else by prefix (so
    `podium:developer` finds `podium:developer a849d9`). An empty `item` names nothing."""
    item = clip(item)
    if not item:
        return []
    runners = [one.get('agent', '') for one in rows]
    if agent is not None and agent != '':
        agent = clip(agent)
        exact = agent in runners
        keep = [at for at, runner in enumerate(runners) if runner == agent or (not exact and runner.startswith(agent))]
    else:
        keep = [at for at, runner in enumerate(runners) if agent is None or runner == '']
    exact = [at for at in keep if rows[at].get('item') == item]
    return exact or [at for at in keep if str(rows[at].get('item', '')).startswith(item)]


def one_row(rows, item, agent=None):
    """The index of the single row `item` names, None when none, StatusError when a prefix names several."""
    found = find(rows, item, agent)
    if len(found) > 1:
        raise StatusError('%r names %d steps (%s); give more of the name' % (
            item, len(found), '; '.join(rows[at]['item'] for at in found[:5])))
    return found[0] if found else None


def put_row(data, item, state, figure, waiting, step=None, after=None):
    """Add the row, or replace the one of the same name and runner in place; a new row goes after `after` if given.

    The anchor is found by its name alone (an agent's step may follow a step of this session), this runner's first."""
    row = dict({'item': clip(item), 'state': clip(state), 'figure': clip(figure), 'waiting': clip(waiting)},
               **dict({key: '' for key in STEP_FIELDS}, **(step or {})))
    rows = [dict(one) for one in data['rows']]
    at = next((i for i, one in enumerate(rows) if same(one, row['item'], row['agent'])), None)
    if at is not None:
        rows[at] = row
        return dict(data, rows=rows)
    anchors = find(rows, after, row['agent']) or find(rows, after) if after else []
    rows.insert(len(rows) if not anchors else anchors[0] + 1, row)
    return dict(data, rows=rows)


def drop_row(data, item, agent=''):
    """Remove the step `item` names (exactly, else by a unique prefix); nothing named, nothing removed."""
    at = one_row(data['rows'], item, agent)
    return data if at is None else dict(data, rows=[one for i, one in enumerate(data['rows']) if i != at])


def rename_row(data, old, new, agent=''):
    """Give the step `old` names the name `new`, in place; it must exist, be one step, and not collide with another."""
    rows = [dict(one) for one in data['rows']]
    at = one_row(rows, old, agent)
    if at is None:
        raise StatusError('no step named %r' % old)
    if not clip(new):
        raise StatusError('a step needs a name')
    if any(same(one, clip(new), rows[at].get('agent', '')) for i, one in enumerate(rows) if i != at):
        raise StatusError('a step named %r already exists' % new)
    rows[at]['item'] = clip(new)
    return dict(data, rows=rows)


def running_item(data):
    """The name of the step of this session that runs now (the first one), or ''."""
    return next((row['item'] for row in data['rows'] if not row.get('agent') and row.get('state') == 'running'), '')
