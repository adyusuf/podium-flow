"""This session's spending for the Status box (user decision 06/11/2026): MEASURED, shown, never a stop.

The money budget no longer stops or gates any work (it used to be the autonomous run's $100 ceiling, #20). What is left
is a figure the user follows in the Status box: what this session has spent so far against the panel's
`budget.session_usd` ('none' shows the spend alone).

The spend is the session's transcript plus its subagents' transcripts (`<transcript without .jsonl>/subagents/*.jsonl`),
tokens x the API LIST price (step_stats_transcripts.measure) - a proxy for consumption, not a subscription bill, and the
line says so. A transcript that cannot be read gives no figure rather than a guess (rule #15).
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import step_stats_transcripts as transcripts  # noqa: E402

BUDGETS = ('none', '200', '500', '1000')     # user decision 09/11/2026
LEGACY_BUDGETS = ('25', '50', '100')          # still shown as set, from a file written before then (rule #4)
DEFAULT_BUDGET = '200'


def transcript_paths(path):
    """The session's transcript and its subagents' transcripts that exist."""
    if not path or not os.path.isfile(path):
        return []
    stem = path[:-len('.jsonl')] if path.endswith('.jsonl') else path
    return [path] + sorted(glob.glob(os.path.join(stem, 'subagents', '*.jsonl')))


def spent(path):
    """US dollars at list price for the session behind `path`, or None when nothing could be measured."""
    paths = transcript_paths(path)
    if not paths:
        return None
    try:
        measured = transcripts.measure(paths)
    except OSError:
        return None
    return sum(cost for _first, _count, cost, _model in measured.values()) if measured else None


def budget_setting(session):
    """The panel's budget.session_usd for this session ('none' or a whole number of dollars); the default if unreadable."""
    try:
        import podium_layers
        value = podium_layers.load(session=session)[0].get('budget.session_usd', (DEFAULT_BUDGET, ''))[0]
    except Exception:  # noqa: BLE001 - a hook never fails on the settings; it shows the default budget
        return DEFAULT_BUDGET
    return value if value in BUDGETS + LEGACY_BUDGETS else DEFAULT_BUDGET


def line(amount, budget):
    """The one line the Status box shows. Never a verdict: going over the budget is said, nothing stops."""
    if amount is None:
        return ''
    figure = '$%.2f spent' % amount
    if budget == 'none':
        return '%s · no budget set · measured: tokens × API list price' % figure
    limit = float(budget)
    share = int(round(100 * amount / limit)) if limit else 0
    over = ' — over the budget, shown only: work goes on' if amount > limit else ''
    return '%s of $%s (%d%%)%s · measured: tokens × API list price' % (figure, budget, share, over)


def status_line(session, transcript_path):
    """What the hooks write into the status table's `budget` field ('' when nothing was measured)."""
    return line(spent(transcript_path), budget_setting(session))
