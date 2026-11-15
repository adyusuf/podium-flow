"""The podium configuration as text: the `show` table, the block a session starts with (`context`) and the agent list.

Split out of podium_config.py so no file passes 300 lines (rule #9); podium_config.py re-exports every name here.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import podium_session as sessions  # noqa: E402
from podium_schema import E2E_STAGES, ROOT, SCHEMA, TARGETS, agents, gate_steps_off  # noqa: E402


def shown(value):
    return 'yes' if value is True else 'no' if value is False else str(value)


def render(effective, problems):
    lines = []
    group = None
    for spec in SCHEMA:
        if spec['group'] != group:
            group = spec['group']
            lines.append(group)
        value, source = effective[spec['key']]
        lines.append('  %-34s %-8s %s' % (spec['key'], shown(value), '' if source == 'default' else '(%s)' % source))
    lines.extend('! ' + problem for problem in problems)
    return '\n'.join(lines)


# What each reply length asks of Claude, printed at session start (standards/00-working-method.md §5a). Whatever the
# length, a red test, a skipped step, an open finding and what waits on the user are said: shorter, never left out.
REPLY_MEANING = {
    'short': 'the important points first and, said plainly, what the user must do or decide; no long back-and-forth. '
             'Anything long (evidence, per-step detail, logs, long tables, the end-of-turn completeness block) goes '
             'inside a collapsed <details><summary>...</summary>...</details> section, never left out. Still said at every '
             'length: a red test, a skipped step, an open finding, what waits on the user, the long-run table, the #28 '
             'handoff line and end-of-turn block, the #24 deferred list, the #27 agent count and cost (standards/00 §5a)',
    'normal': 'the result and the reasoning that matters, short lists where they help (standards/00 §5a)',
}


def context(effective, problems, session=None):
    """The compact block a session starts with: the effective values, what they mean, how to change them."""
    value = lambda key: effective[key][0]  # noqa: E731
    steps = []
    for target in TARGETS:
        steps.append('%s: merge %s, gates before push %s, coverage before push %s, push %s, CI after push %s' % (
            target, shown(value('merge.' + target)), shown(value('gates_before_push.' + target)),
            shown(value('coverage_before_push.' + target)), shown(value('push.' + target)),
            shown(value('ci_after_push.' + target))))
        off = gate_steps_off({key: pair[0] for key, pair in effective.items()}, target)
        if off and value('gates_before_push.' + target):     # an unticked step is waived and named (02/11/2026)
            steps[-1] += ', gate steps off (waived, named in Gate-Waived): %s' % ', '.join(off)
    steps.append('e2e before deploy: ' + ', '.join(
        'on %s before deploying %s %s' % (on, after, shown(value('e2e_before_deploy.' + after))) for on, after in E2E_STAGES))
    lines = ['podium configuration (effective; global rule #34 - follow it, do not ask what it answers):',
             '  for code work: changing a project repository\'s files. A no-code task (a question, research, Claude\'s own '
             'bookkeeping in ~/.claude) makes no branch or commit and runs no merge, push, gate, coverage, CI, deploy, e2e, '
             'test writing or agent; replies, the Status box and #14/#15/#24 still apply (standards/13 §8a).',
             '  mode %s, model for the Opus agents: %s' % (value('mode'), value('mode_model')),
             '  replies: %s - %s' % (value('reply.length'), REPLY_MEANING.get(value('reply.length'), REPLY_MEANING['short'])),
             '  pod: connect %s, message format %s (stored only; nothing acts on it)' % (
                 shown(value('pod.connect')), value('pod.message_format')),
             '  write unit tests: %s, write e2e: %s' % (shown(value('write.unit_tests')), shown(value('write.e2e')))]
    if not value('write.unit_tests'):
        lines.append('    tests: do not write; suites/gates/coverage/CI/e2e: run only where the keys below say yes, '
                     'else "not run (configuration)" (neither pass nor fail); global #8/#31/#32 are HOW, never a trigger '
                     '- they do not start test work (#34).')
    active = agents({k: v[0] for k, v in effective.items()})
    lines.append('  agents: %s' % (', '.join('%s (%s)' % (row['role'], row['runs_on']) for row in active) or 'none'))
    lines.extend('  ' + step for step in steps)
    lines.append('  change it with the podium:config skill; the mode may also be set per session or per project.')
    if sessions.valid(session):
        lines.append('  this session is %s: what the rail boxes change applies to it only (podium_config.py set --session %s '
                     '<key> <value>); a new session starts from the saved defaults.' % (session, session))
        lines.append('  status box and steps (steps.enforce: %s): analyse every task first and write its steps, in order, '
                     'before acting: python3 "%s" --session %s step "<n. short name>" "<state>" <percent> [--blocker "<what>"] '
                     '[--after "<step>"] [--note "<details>"]; a new request mid-work goes in as steps with --after. Keep state (not started, '
                     'running, done, blocked, did not run) and %% current; now|next <text> say what runs. The hooks set now '
                     'on each message and "waiting for you" at each turn\'s end (standards/00 §1a, §10d).'
                     % (value('steps.enforce'), os.path.join(ROOT, 'scripts', 'podium_status.py'), session))
    lines.extend('  ! ' + problem for problem in problems)
    return '\n'.join(lines)


def render_agents(values):
    rows = agents(values)
    if not rows:
        return 'mode %s runs no agents.' % values['mode']
    lines = ['mode %s - %d agent(s); Opus agents run on: %s (a per-agent model beats it)' % (values['mode'], len(rows), values['mode_model'])]
    lines.extend('  %-18s defined %-7s runs on %s%s' % (r['role'], r['defined'], r['runs_on'],
                 '' if r['enabled'] == 'auto' else '   [%s]' % r['enabled']) for r in rows)
    return '\n'.join(lines)
