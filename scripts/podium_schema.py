"""The podium configuration's schema: what can be set, the role sets of the modes, and the agents each mode runs.

Split out of podium_config.py so no file passes 300 lines (rule #9); podium_config.py re-exports every name here.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS_FILE = os.path.join(ROOT, 'defaults', 'podium.json')
TARGETS = ('dev', 'test', 'prod')
E2E_STAGES = (('dev', 'test'), ('test', 'prod'))      # (the environment e2e runs on, the target about to be deployed)
MODES = ('A', 'B', 'C', 'D', 'E')
MODELS = ('keep', 'sonnet', 'haiku', 'fable')
# Settings that no longer exist. A user's file written before they were retired still holds them: they are skipped
# on read, so one stale key never makes the whole layer invalid (and the next write drops them).
RETIRED_KEYS = (('monitor.connect', 'monitor.message_format')
                + tuple('run_before_push.%s.%s' % (t, gate) for t in TARGETS for gate in ('unit', 'e2e'))
                + tuple('%s.%s' % (group, t) for group in ('ci_before_merge', 'e2e_after_deploy') for t in TARGETS)
                + ('deploy_after_push',))      # one radio choice until 30/10/2026; now deploy_after_push.<test|prod> checkboxes


def _bool(key, label):
    return {'key': key, 'type': 'bool', 'label': label}


def _enum(key, label, options):
    return {'key': key, 'type': 'enum', 'label': label, 'options': list(options)}


# The role sets of the modes (modes/README.md; the test pins them to the agent files and the mode documents).
# Each mode's set contains the one before it (B in C in D); E is D with parallel Workflow agents.
B_ROLES = ('analyst', 'test-writer', 'doc-writer')
C_ROLES = ('product-manager', 'analyst', 'architect', 'designer', 'developer', 'test-writer', 'qa', 'devops', 'doc-writer')
D_ROLES = C_ROLES + ('data', 'observability', 'security', 'coverage-auditor', 'e2e-writer')
MODE_ROLES = {'A': (), 'B': B_ROLES, 'C': C_ROLES, 'D': D_ROLES, 'E': D_ROLES}
AGENTS_DIR = os.path.join(ROOT, 'agents')


POD_FORMATS = ('short', 'full')
REPLY_LENGTHS = ('short', 'normal', 'long')       # how much Claude writes in a reply (standards/00 §5a)
STEP_ENFORCEMENT = ('block', 'remind')            # steps first: refuse a code edit until the Status box holds steps, or remind
DEPLOY_ENVS = ('test', 'prod')                    # which environment a push is deployed to
CI_RUNNERS = ('hosted', 'self-hosted')            # where the shared SDLC workflow runs (self-hosted: this Mac's runners)
AGENT_STATES = ('auto', 'on', 'off')
AGENT_MODELS = ('default', 'opus', 'sonnet', 'haiku', 'fable')
GATE_LIB = os.path.join(ROOT, 'scripts', 'gate-lib.sh')


def gate_steps(path=GATE_LIB):
    """[(id, name, heading)] of the gate's steps, read from GATE_STEPS in gate-lib.sh: the one list of them (rule #2;
    user decision 02/11/2026). An unreadable file gives none, so the pane shows no step rows rather than a guessed list.
    A fourth column `locked` marks a step nobody can untick; locked_steps() reads it."""
    try:
        with open(path, encoding='utf-8') as handle:
            found = re.search(r"^GATE_STEPS='(.*?)'", handle.read(), re.S | re.M)
    except OSError:
        return []
    return [row[:3] for row in _rows(found.group(1)) if len(row) in (3, 4)] if found else []


def _rows(block):
    rows = [tuple(part.strip() for part in line.split('|')) for line in block.splitlines()]
    return [row for row in rows if re.fullmatch(r'[a-z0-9_]+', row[0]) and (len(row) == 3 or row[3:] == ('locked',))]


def locked_steps(path=GATE_LIB):
    """The ids of the steps marked `locked` in GATE_STEPS: the secret scan and SAST (user decision 02/11/2026; rule #19
    says they are never switched off). Their ticks cannot be turned off and the gate runs them whatever the file says."""
    try:
        with open(path, encoding='utf-8') as handle:
            found = re.search(r"^GATE_STEPS='(.*?)'", handle.read(), re.S | re.M)
    except OSError:
        return []
    return [row[0] for row in _rows(found.group(1)) if len(row) == 4] if found else []


GATE_STEPS = tuple(gate_steps())
LOCKED_STEPS = tuple(locked_steps())


# The one definition of what can be set: order is the display order. `group` titles the sections of `show`.
SCHEMA = (
    [dict(_enum('mode', 'Working mode', MODES), group='Session'),
     dict(_enum('mode_model', 'Model that replaces Opus in the agents', MODELS), group='Session'),
     dict(_enum('reply.length', 'Reply length', REPLY_LENGTHS), group='Session'),
     dict(_enum('steps.enforce', 'Steps first', STEP_ENFORCEMENT), group='Session'),
     dict(_bool('pod.connect', 'Connect to pod'), group='Pod'),
     dict(_enum('pod.message_format', 'Message format', POD_FORMATS), group='Pod'),
     dict(_bool('write.unit_tests', 'Write unit tests'), group='Writing'),
     dict(_bool('write.e2e', 'Write e2e specs'), group='Writing')]
    + [dict(_bool('merge.' + t, 'Merge into ' + t), group='Merge') for t in TARGETS]
    + [dict(_bool('push.' + t, 'Push ' + t), group='Push') for t in TARGETS]
    + [dict(_bool('gates_before_push.' + t, 'Run gates before pushing %s' % t), group='Gates before a push') for t in TARGETS]
    + [dict(_bool('coverage_before_push.' + t, 'Run coverage before pushing %s' % t), group='Coverage before a push')
       for t in TARGETS]
    # One tick per step of the gate and target; each defaults to on here, not in defaults/podium.json, so the step list
    # is written only in gate-lib.sh. `step` and `heading` are what the pane shows and its hover card says.
    + [dict(_bool('gate_steps.%s.%s' % (step, t), 'Gate step %s on %s' % (name, t)), group='Gate steps', step=name,
            heading=heading, default=True, **({'locked': True} if step in LOCKED_STEPS else {}))
       for step, name, heading in GATE_STEPS for t in TARGETS]
    + [dict(_bool('ci_after_push.' + t, 'Run CI after pushing %s' % t), group='CI after push') for t in TARGETS]
    + [dict(_bool('deploy_after_push.' + env, 'After pushing update, deploy to ' + env), group='Deploy after push') for env in DEPLOY_ENVS]
    + [dict(_enum('ci.runner', 'CI runner', CI_RUNNERS), group='CI after push')]
    + [dict(_bool('e2e_before_deploy.' + after, 'Run e2e on %s before deploying %s' % (on, after)), group='E2E before deploy')
       for on, after in E2E_STAGES]
    + [dict(_enum('agents.%s.%s' % (role, field), '%s: %s' % (role, field), options), group='Agents')
       for role in D_ROLES for field, options in (('enabled', AGENT_STATES), ('model', AGENT_MODELS))])
SPECS = {spec['key']: spec for spec in SCHEMA}


def gate_steps_off(values, target):
    """The ids of the gate's steps unticked for `target` (a value other than False runs the step): the gate prints the
    id, so the Gate-Waived line names the same word (qa 02/11/2026)."""
    return [step for step, _, _ in GATE_STEPS if values.get('gate_steps.%s.%s' % (step, target)) is False]


def front_matter(role, field, missing):
    """One front-matter line of an agent file (`model:`, `description:`), or `missing` when the file or line is absent."""
    try:
        with open(os.path.join(AGENTS_DIR, role + '.md'), encoding='utf-8') as handle:
            for line in handle:
                if line.startswith(field + ':'):
                    return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return missing


def defined_model(role):
    """The model an agent file names (its `model:` front-matter line), or 'inherit'."""
    return front_matter(role, 'model', 'inherit')


def effective_model(defined, override):
    """Only the Opus agents move to the mode's override; `keep` (and no override) leaves every agent as defined."""
    return override if defined == 'opus' and override not in ('keep', 'opus', None) else defined


def agents(values, include_inactive=False):
    """One dict per role: defined model, the model it runs on, the model `default` gives it (`default_model`, also while
    another is pinned: the pane's model radios need it), whether it is active, and the settings behind that.

    A role is active when `agents.<role>.enabled` is `on`, or `auto` and the mode's set holds it; mode A runs none
    whatever the settings say. `agents.<role>.model` other than `default` beats the mode's Opus override."""
    mode, override = values['mode'], values['mode_model']
    rows = []
    for role in D_ROLES:
        in_mode = role in MODE_ROLES.get(mode, ())
        enabled = values.get('agents.%s.enabled' % role, 'auto')
        active = False if mode == 'A' else (in_mode if enabled == 'auto' else enabled == 'on')
        defined = defined_model(role)
        chosen = values.get('agents.%s.model' % role, 'default')
        default_model = effective_model(defined, override)
        runs_on = chosen if chosen != 'default' else default_model
        if active or include_inactive:
            rows.append({'role': role, 'defined': defined, 'runs_on': runs_on, 'default_model': default_model, 'active': active,
                         'in_mode': in_mode, 'enabled': enabled, 'model': chosen,
                         'description': front_matter(role, 'description', '')})   # the pane's hover card (01/11/2026)
    return rows
