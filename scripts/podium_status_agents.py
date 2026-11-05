"""The Status box's rows for subagents, written by the HOOKS and never by the agent (user decision 05/11/2026).

    start   SubagentStart: a `task` step of the agent opens, running, with no % (nothing measures one)
    tick    PostToolUse of a subagent's tool call: the step's note is refreshed with the tool calls and the time so far
    stop    SubagentStop: the step is done (100%) or failed, its note the duration, the tool calls and the output tokens;
            any other step of that agent still open is closed the same way, so no row is left running after the agent ends

Every figure is MEASURED: the duration is the stop time minus the start time the row recorded; a tool call is counted
from the hook calls or, at the stop, from the agent's own transcript; output tokens are summed from that transcript; the
model is shown only when the hook payload names it. A figure with no signal is left out, never estimated.
Pure functions over the table `data`: the caller holds the lock and saves.
"""
import json
import os

from podium_status_rows import CLOSED, clip, one_row, put_row

AGENT_STEP = 'task'            # the one step the hooks write for an agent
FAILED_STATUS = ('failed', 'error', 'errored', 'cancelled', 'canceled', 'interrupted', 'aborted')
MAX_TRANSCRIPT = 64 * 1024 * 1024


def agent_name(payload):
    """How a subagent is named in the box: its type and the start of its id, so two of a kind stay apart."""
    return ('%s %s' % (str(payload.get('agent_type') or 'agent'), str(payload.get('agent_id') or '')[:6])).strip()


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


def note_of(model, seconds, tool_uses, out_tokens):
    """The step's note from what was measured; a part with no signal (None) is left out."""
    parts = [clip(model) if model else None, None if seconds is None else duration(seconds),
             None if tool_uses is None else '%d tool use%s' % (tool_uses, '' if tool_uses == 1 else 's'),
             None if out_tokens is None else '%s out tokens' % tokens(out_tokens)]
    return ' · '.join(part for part in parts if part)


def transcript_counts(path):
    """(tool calls, output tokens) read from an agent's transcript (JSON lines), or None when it cannot be read.

    A message may be written on several lines: a tool call counts once by its id, a message's tokens once by its id."""
    try:
        if not path or not os.path.isfile(path) or os.path.getsize(path) > MAX_TRANSCRIPT:
            return None
        calls, out = set(), {}
        with open(path, encoding='utf-8', errors='replace') as handle:
            for line in handle:
                try:
                    message = (json.loads(line) or {}).get('message') or {}
                except (ValueError, AttributeError):
                    continue
                for block in message.get('content') if isinstance(message.get('content'), list) else []:
                    if isinstance(block, dict) and block.get('type') == 'tool_use':
                        calls.add(block.get('id') or len(calls))
                usage = message.get('usage')
                if isinstance(usage, dict) and isinstance(usage.get('output_tokens'), int):
                    key = message.get('id') or len(out)
                    out[key] = max(out.get(key, 0), usage['output_tokens'])
        return len(calls), sum(out.values())
    except OSError:
        return None


def number(payload, *names):
    """The first of `names` the payload gives as a non-negative number, else None."""
    for name in names:
        value = payload.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def failure(payload):
    """Why the agent ended in error, or '' when the payload does not say it did (it is then taken as finished)."""
    error = payload.get('error')
    if error:
        return clip(error) if isinstance(error, str) else 'error'
    if payload.get('is_error') is True:
        return 'error'
    status = str(payload.get('status') or '').lower()
    return status if status in FAILED_STATUS else ''


def start(data, payload, now):
    """Open the agent's step, running, replacing an earlier one of the same agent (a resumed agent starts again)."""
    model = clip(payload.get('model'))
    step = {'agent': agent_name(payload), 'since': str(int(now)), 'tools': '0', 'model': model, 'note': note_of(model, None, None, None)}
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
    row.update(tools=str(count), note=note_of(row.get('model'), now - int(row['since']), count, None))
    return dict(data, rows=[row if i == at else one for i, one in enumerate(data['rows'])])


def measured(payload, row, now):
    """(seconds, tool calls, output tokens) of an ended agent, each None when nothing measured it. The payload's own
    figure wins, then the transcript, then what the hooks counted."""
    counted = transcript_counts(str(payload.get('agent_transcript_path') or ''))
    millis, calls, out = number(payload, 'duration_ms'), number(payload, 'tool_uses'), number(payload, 'output_tokens')
    seconds = millis / 1000 if millis is not None else (now - int(row['since']) if hooked(row) else None)
    if calls is None:
        hooks_counted = int(row['tools']) if hooked(row) and str(row.get('tools')).isdigit() else 0
        calls = counted[0] if counted else (hooks_counted or None)       # 0 from the hooks may only mean they saw no call
    if out is None and counted:
        out = counted[1]
    return seconds, None if calls is None else int(calls), None if out is None else int(out)


def stop(data, payload, now):
    """Close the agent's step: done at 100%, or failed. Its other steps still open are closed the same way."""
    agent = agent_name(payload)
    why = failure(payload)
    state, percent = ('failed', '') if why else ('done', '100')
    at = one_row(data['rows'], AGENT_STEP, agent)
    row = dict(data['rows'][at]) if at is not None else {'item': AGENT_STEP, 'agent': agent, 'waiting': '', 'since': '', 'tools': ''}
    model = clip(payload.get('model')) or row.get('model', '')
    seconds, calls, out = measured(payload, row, now)
    row.update(state=state, percent=percent, blocker=why, model=model, note=note_of(model, seconds, calls, out),
               figure=percent + '%' if percent else '')
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
