"""The Status box's rows for subagents, written by the HOOKS and never by the agent (user decision 05/11/2026).

    start   SubagentStart: a `task` step of the agent opens, running, with no % (nothing measures one), labelled
            `<description> (<model>)` from the agent's meta file; a resumed agent (SendMessage) reopens its own row,
            counts `resumed xN` and keeps its time and tool calls instead of starting from zero
    tick    PostToolUse of a subagent's tool call: the step's note is refreshed with the tool calls and the time so far
    stop    SubagentStop: the step is done or failed - failed when the payload says so or the agent's transcript ends on
            an API error (a usage limit: "rate limit"); never from the agent's own report. Its note is the duration, the
            tool calls and the output tokens; any other step of that agent still open is closed the same way

Every figure is MEASURED: the duration is the stop time minus the start time the row recorded; a tool call is counted
from the hook calls or, at the stop, from the agent's own transcript; output tokens are summed from that transcript; the
model is shown only when the hook payload names it. A figure with no signal is left out, never estimated.
Pure functions over the table `data`: the caller holds the lock and saves.
"""
import json
import os
import re

from podium_status_rows import CLOSED, clip, one_row, put_row

AGENT_STEP = 'task'            # the one step the hooks write for an agent
FAILED_STATUS = ('failed', 'error', 'errored', 'cancelled', 'canceled', 'interrupted', 'aborted')
MAX_TRANSCRIPT = 64 * 1024 * 1024     # also the budget line's cap (podium_budget.py)


def agent_name(payload):
    """How a subagent is named in the box: its type and the start of its id, so two of a kind stay apart."""
    return ('%s %s' % (str(payload.get('agent_type') or 'agent'), str(payload.get('agent_id') or '')[:6])).strip()


def meta_of(payload):
    """The agent's meta file the harness writes beside its transcript (`description`, `agentType`, `model`), {} when it
    cannot be read: `<session transcript without .jsonl>/subagents/agent-<id>.meta.json`."""
    path = str(payload.get('agent_transcript_path') or '')
    if path.endswith('.jsonl'):
        meta = path[:-len('.jsonl')] + '.meta.json'
    else:
        session, agent = str(payload.get('transcript_path') or ''), str(payload.get('agent_id') or '')
        if not session.endswith('.jsonl') or not re.match(r'^[\w-]+$', agent):
            return {}
        meta = os.path.join(session[:-len('.jsonl')], 'subagents', 'agent-%s.meta.json' % agent)
    try:
        with open(meta, encoding='utf-8') as handle:
            found = json.load(handle)
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def short_model(name):
    """`claude-sonnet-5-5` -> `Sonnet 5.5`; an alias (`sonnet`) or anything else is shown as given."""
    found = re.match(r'^claude-([a-z]+)-(\d+)-(\d+)', str(name or ''))
    return '%s %s.%s' % (found.group(1).capitalize(), found.group(2), found.group(3)) if found else clip(name)


def label_of(meta, model):
    """How the agent is titled in the box: `<description> (<model>)`, the description alone, or '' with no description."""
    description = clip(meta.get('description'))
    return ('%s (%s)' % (description, model) if model else description) if description else ''


def duration(seconds):
    """`45s`, `3m12s`, `1h05m`: whole seconds, no decimals."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return '%ds' % seconds
    if seconds < 3600:
        return '%dm%02ds' % divmod(seconds, 60)
    return '%dh%02dm' % (seconds // 3600, seconds % 3600 // 60)


def tokens(count):
    return str(count) if count < 1000 else '%.1fk' % (count / 1000)


def note_of(model, seconds, tool_uses, out_tokens, resumed=0):
    """The step's note from what was measured; a part with no signal (None) is left out."""
    parts = [clip(model) if model else None, None if seconds is None else duration(seconds),
             None if tool_uses is None else '%d tool use%s' % (tool_uses, '' if tool_uses == 1 else 's'),
             None if out_tokens is None else '%s out tokens' % tokens(out_tokens),
             'resumed \u00d7%d' % resumed if resumed else None]
    return ' · '.join(part for part in parts if part)


def transcript_counts(path):
    """(tool calls, output tokens) read from an agent's transcript (JSON lines), or None when it cannot be read."""
    facts = transcript_facts(path)
    return None if facts is None else (facts['calls'], facts['out'])


def transcript_facts(path):
    """What an agent's transcript (JSON lines) measures, or None when it cannot be read: `calls` and `out` (tool calls
    and output tokens over every run), `model` (the model of its last answer) and `error` (the error its LAST answer ended
    on - `rate_limit` when a usage limit stopped it - or '' when the last answer is not an error).

    A message may be written on several lines: a tool call counts once by its id, a message's tokens once by its id."""
    try:
        if not path or not os.path.isfile(path) or os.path.getsize(path) > MAX_TRANSCRIPT:
            return None
        calls, out, model, error = set(), {}, '', ''
        with open(path, encoding='utf-8', errors='replace') as handle:
            for line in handle:
                try:
                    entry = json.loads(line) or {}
                    message = entry.get('message') or {}
                except (ValueError, AttributeError):
                    continue
                if not isinstance(message, dict):
                    continue
                if entry.get('type') == 'assistant':
                    error = str(entry.get('error') or entry.get('apiError') or 'error') if entry.get('isApiErrorMessage') else ''
                    model = str(message.get('model') or model)
                for block in message.get('content') if isinstance(message.get('content'), list) else []:
                    if isinstance(block, dict) and block.get('type') == 'tool_use':
                        calls.add(block.get('id') or len(calls))
                usage = message.get('usage')
                if isinstance(usage, dict) and isinstance(usage.get('output_tokens'), int):
                    key = message.get('id') or len(out)
                    out[key] = max(out.get(key, 0), usage['output_tokens'])
        return {'calls': len(calls), 'out': sum(out.values()), 'model': model, 'error': error}
    except OSError:
        return None


def number(payload, *names):
    """The first of `names` the payload gives as a non-negative number, else None."""
    for name in names:
        value = payload.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def failure(payload, facts=None):
    """Why the agent ended in error, or '' when neither the payload nor its transcript says it did (it is then taken as
    finished). The transcript counts only when its LAST answer is an API error: an agent stopped by a usage limit and
    resumed later ends done (seen in agent-ada8eb8363b165ea1.jsonl, 15/11/2026)."""
    error = payload.get('error')
    if error:
        return clip(error) if isinstance(error, str) else 'error'
    if payload.get('is_error') is True:
        return 'error'
    status = str(payload.get('status') or '').lower()
    if status in FAILED_STATUS:
        return status
    last = (facts or {}).get('error') or ''
    return 'rate limit' if last in ('rate_limit', 'usage_limit_reached') else clip(last)


def whole(value):
    """A stored whole number, 0 when the field is empty or not a number."""
    return int(value) if str(value or '').isdigit() else 0


def start(data, payload, now):
    """Open the agent's step, running. A resumed agent (its row is already there and over) reopens the same row: the
    time and tool calls of its earlier runs carry on and `resumed` counts up (layer 2, 16/11/2026)."""
    agent, meta = agent_name(payload), meta_of(payload)
    at = one_row(data['rows'], AGENT_STEP, agent)
    old = data['rows'][at] if at is not None and hooked(data['rows'][at]) else None
    model = clip(payload.get('model')) or (old or {}).get('model', '') or short_model(meta.get('model'))
    spent, tools, resumed = 0, 0, 0
    if old is not None and old.get('state') == 'running':        # a second start of a run already open: no new run
        spent, tools, resumed, since = whole(old.get('spent')), whole(old.get('tools')), whole(old.get('resumed')), old['since']
    else:
        if old is not None:
            spent, tools, resumed = whole(old.get('spent')), whole(old.get('tools')), whole(old.get('resumed')) + 1
        since = str(int(now))
    label = label_of(meta, model) or (old or {}).get('label', '')
    step = {'agent': agent, 'since': since, 'tools': str(tools), 'model': model, 'label': label, 'spent': str(spent),
            'resumed': str(resumed) if resumed else '',
            'note': note_of(model, spent if old is not None else None, tools if old is not None else None, None, resumed)}
    return put_row(data, AGENT_STEP, 'running', '', '', step)


def hooked(row):
    """Whether a row was written by the hooks (it records when it started)."""
    return str(row.get('since') or '').isdigit()


def tick(data, payload, now):
    """One more tool call by the agent: refresh its step's note. No step of this agent, or one already over: unchanged."""
    at = one_row(data['rows'], AGENT_STEP, agent_name(payload))
    if at is None or data['rows'][at].get('state') != 'running' or not hooked(data['rows'][at]):
        return data
    row = dict(data['rows'][at])
    count = int(row['tools']) + 1 if str(row.get('tools') or '').isdigit() else 1
    row.update(tools=str(count), note=note_of(row.get('model'), whole(row.get('spent')) + now - int(row['since']), count, None,
                                              whole(row.get('resumed'))))
    return dict(data, rows=[row if i == at else one for i, one in enumerate(data['rows'])])


def measured(payload, row, now, facts=None):
    """(seconds, tool calls, output tokens) of an ended agent over ALL its runs, each None when nothing measured it. The
    payload's own figure wins, then the transcript, then what the hooks counted - except for a resumed agent, whose
    payload counts one run while its transcript holds them all: there the transcript wins."""
    counted = None if facts is None else (facts['calls'], facts['out'])
    millis, calls, out = number(payload, 'duration_ms'), number(payload, 'tool_uses'), number(payload, 'output_tokens')
    run = millis / 1000 if millis is not None else (now - int(row['since']) if hooked(row) else None)
    seconds = None if run is None else whole(row.get('spent')) + run
    if whole(row.get('resumed')):
        calls = counted[0] if counted else (whole(row.get('tools')) or calls)
        out = counted[1] if counted else None
    if calls is None:
        hooks_counted = int(row['tools']) if hooked(row) and str(row.get('tools')).isdigit() else 0
        calls = counted[0] if counted else (hooks_counted or None)       # 0 from the hooks may only mean they saw no call
    if out is None and counted:
        out = counted[1]
    return seconds, None if calls is None else int(calls), None if out is None else int(out)


def stop(data, payload, now):
    """Close the agent's step: done at 100%, or failed. Its other steps still open are closed the same way."""
    agent = agent_name(payload)
    facts = transcript_facts(str(payload.get('agent_transcript_path') or ''))
    why = failure(payload, facts)
    # No % on an agent's row: nothing measures how much of its work is done, and "done 100" was read as a measurement.
    state, percent = ('failed', '') if why else ('done', '')
    at = one_row(data['rows'], AGENT_STEP, agent)
    row = dict(data['rows'][at]) if at is not None else {'item': AGENT_STEP, 'agent': agent, 'waiting': '', 'since': '', 'tools': ''}
    model = clip(payload.get('model')) or short_model((facts or {}).get('model')) or row.get('model', '')
    seconds, calls, out = measured(payload, row, now, facts)
    label = label_of(meta_of(payload), model) or row.get('label', '')
    row.update(state=state, percent=percent, blocker=why, model=model, label=label, figure='',
               spent=str(int(seconds)) if seconds is not None else row.get('spent', ''),
               tools=str(calls) if calls is not None else row.get('tools', ''),   # a resume counts on from here
               note=note_of(model, seconds, calls, out, whole(row.get('resumed'))))
    rows = list(data['rows'])
    if at is None:
        rows.append(row)
    else:
        rows[at] = row
    # Any other step of this agent that was still open ends with it: left alone it would show running for ever.
    for i, one in enumerate(rows):
        if one.get('agent') == agent and i != at and one is not row and one.get('state') not in CLOSED + ('failed',):
            rows[i] = dict(one, state=state, percent=percent or one.get('percent', ''), blocker=why or one.get('blocker', ''))
    return dict(data, rows=rows)
