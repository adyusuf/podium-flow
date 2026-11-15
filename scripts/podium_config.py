#!/usr/bin/env python3
"""The podium configuration: defaults instead of questions.

    podium_config.py show [--json] [--user]     every setting, its value and where the value comes from (--user: only the
                                                 shipped defaults and the user's own file, no project or session layer)
    podium_config.py get <key>                  one effective value
    podium_config.py set <key> <value> [--project|--session ID]   change one setting (default scope: the user's)
    podium_config.py unset <key> [--project|--session ID]         fall back to the next layer
    podium_config.py apply <file|-> [--project|--session ID]      set many at once from a JSON object {"push.prod": false, ...}
    (--session ID: show, get, agents and context also read that session's layer)
    podium_config.py schema                     the keys with type, options and label
    podium_config.py agents [--json] [--all]    the active agents and the model each one runs on (--all: inactive too)
    podium_config.py reset-agents [--project]   remove every agents.<role>.* setting (back to the mode's own set)
    podium_config.py context [--stdin]          the block the SessionStart hook prints (--stdin: take the session id from the hook payload)
    podium_config.py notify <event>             hook: tells the running session when a setting changed (stdin: the payload)

Layers, lowest first: defaults/podium.json (shipped with the plugin) < ~/.claude/podium.json (the user's own
defaults) < <project>/.claude/podium.json (committed, like .claude/mode) < the session's own layer (podium_session.py:
what the rail boxes change; gone with the session). The user changes them with the
`podium:config` skill; Claude never asks what a setting already answers (global rule #34).

Keys are dotted (`push.prod`); files hold them nested. A key is validated against SCHEMA, a file that does not
parse is reported and ignored (the layer below wins) - the SessionStart hook must never fail a session.
Exit codes: 0 done · 1 a configuration file is unreadable (set/unset/apply refuse to overwrite it) ·
2 bad usage, unknown key or invalid value (nothing is written).
"""
import json
import os
import sys
import tempfile

# The schema, the layers and the text live beside this file (split so no file passes 300 lines, rule #9); every name
# they hold is re-exported here, so callers keep reading them from podium_config.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import podium_session as sessions  # noqa: E402
from podium_schema import (  # noqa: E402,F401
    AGENTS_DIR, AGENT_MODELS, AGENT_STATES, B_ROLES, CI_RUNNERS, C_ROLES,
    DEFAULTS_FILE, DEPLOY_ENVS, D_ROLES, E2E_STAGES, GATE_STEPS, LOCKED_STEPS, MODELS, MODES,
    MODE_ROLES, POD_FORMATS, REPLY_LENGTHS, RETIRED_KEYS, ROOT, SCHEMA,
    SPECS, TARGETS, agents, defined_model, effective_model, front_matter, gate_steps_off)
from podium_layers import (  # noqa: E402,F401
    ConfigError, check, flatten, load, locked, nest,
    project_file, read_layer, user_file, write_layer)
from podium_render import REPLY_MEANING, context, render, render_agents, shown  # noqa: E402,F401


def seen_dir():
    return os.environ.get('PODIUM_SEEN_DIR') or os.environ.get('ADYUSUF_SEEN_DIR') or os.path.join(os.path.expanduser('~'), '.claude', 'podium-seen')


def notify(event, payload_text):
    """A hook (UserPromptSubmit, PostToolUse): when the effective settings differ from what this session last saw,
    answer with additionalContext naming the changes. The first call of a session only records them (SessionStart already
    printed them). The note says the change applies from the NEXT task, so a running one is never split. Never raises."""
    try:
        session = str(json.loads(payload_text).get('session_id') or '')
    except (ValueError, AttributeError):
        session = ''
    if not sessions.valid(session):         # the one rule for a session id that becomes a file name (F-032)
        return None
    effective, problems = load(session=session)
    values = {key: value[0] for key, value in effective.items()}
    path = os.path.join(seen_dir(), session)
    try:
        with open(path, encoding='utf-8') as handle:
            before = json.load(handle)
    except (OSError, ValueError):
        before = None
    def remember():
        """A temporary file renamed over: a reader never sees a half-written seen-file (F-032)."""
        temp = None
        try:
            os.makedirs(seen_dir(), exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=seen_dir(), prefix='.%s-' % session, suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(values, handle)
            os.replace(temp, path)
            return True
        except OSError:
            if temp and os.path.exists(temp):
                os.remove(temp)
            return False

    changes = []
    if isinstance(before, dict):
        before = {key: value for key, value in before.items() if key in SPECS}   # a retired key is not a change
        # A setting the seen-file never had (the plugin was updated mid-session) is new, not changed.
        changes = ['%s: %s -> %s' % (key, shown(before[key]), shown(values[key])) for key in sorted(values)
                   if key in before and before[key] != values[key]]
        if not changes:
            if before != values:
                remember()                      # only new settings appeared: remember them, say nothing
            return None
    if not remember() or before is None:
        return None
    text = ('podium settings changed (/podium:config). Apply them from the NEXT task on; finish the step in progress as it '
            'was started, do not restart or split it. Reply length is the exception: it applies from your next reply. '
            'Changes: ' + '; '.join(changes) + '.\n' + context(effective, problems, session))
    return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': text}}


def payload_session():
    """The session id a hook's JSON payload on stdin carries ('' when it holds none). Only called for `context --stdin`:
    reading stdin would block a run that was not given a payload."""
    try:
        session = json.loads(sys.stdin.read()).get('session_id')
    except (OSError, ValueError, AttributeError):
        return ''
    return session if sessions.valid(session) else ''


def main(argv):
    args = list(argv)
    scope_project = '--project' in args
    scope_user = '--user' in args
    args = [a for a in args if a not in ('--project', '--user')]
    session = None
    if '--session' in args:
        at = args.index('--session')
        session = args[at + 1] if at + 1 < len(args) else ''
        del args[at:at + 2]
    command = args[0] if args else ''
    try:
        if session is not None and not sessions.valid(session):
            raise ConfigError('--session needs a session id (letters, digits, - and _)')
        if session is not None and scope_project:
            raise ConfigError('--project and --session cannot be combined')
        if command in ('show', 'context', 'get', 'schema', 'agents') and scope_project:
            raise ConfigError('--project only applies to set, unset and apply')
        if command in ('set', 'unset', 'apply', 'reset-agents'):
            path = sessions.session_file(session) if session else (project_file() if scope_project else user_file())

        def write(*parts):
            write_layer(*parts)
            if session:
                sessions.prune()                  # a session file nobody has touched for two weeks goes
        if scope_user and (command != 'show' or session is not None):
            raise ConfigError('--user only applies to show, and not with --session')
        if command == 'show':
            effective, problems = load(session=session, project=not scope_user)
            if '--json' in args:
                print(json.dumps({'values': {k: v[0] for k, v in effective.items()}, 'sources': {k: v[1] for k, v in effective.items()},
                                  'problems': problems}, indent=2))
            else:
                print(render(effective, problems))
            return 0
        if command == 'agents':
            effective, _ = load(session=session)
            values = {k: v[0] for k, v in effective.items()}
            if '--json' in args:
                print(json.dumps(agents(values, include_inactive='--all' in args), indent=2))
            else:
                print(render_agents(values))
            return 0
        if command == 'reset-agents':
            write(path, {}, [key for key in SPECS if key.startswith('agents.')])
            print('every agents.* setting removed from %s' % path)
            return 0
        if command == 'context':
            session = session or (payload_session() if '--stdin' in args else '')
            print(context(*load(session=session), session))
            return 0
        if command == 'notify' and len(args) == 2:
            try:
                answer = notify(args[1], sys.stdin.read())
            except Exception:   # a hook must never fail the session it serves
                answer = None
            if answer:
                print(json.dumps(answer))
            return 0
        if command == 'schema':
            print(json.dumps(SCHEMA, indent=2))
            return 0
        if command == 'get' and len(args) == 2:
            effective, _ = load(session=session)
            if args[1] not in effective:
                raise ConfigError("unknown setting '%s'" % args[1])
            print(shown(effective[args[1]][0]))
            return 0
        if command == 'set' and len(args) == 3:
            write(path, {args[1]: check(args[1], args[2])})
            print('%s = %s  (%s)' % (args[1], shown(check(args[1], args[2])), path))
            return 0
        if command == 'unset' and len(args) == 2:
            check_key = args[1]
            if check_key not in SPECS:
                raise ConfigError("unknown setting '%s'" % check_key)
            write(path, {}, (check_key,))
            print('%s removed from %s' % (check_key, path))
            return 0
        if command == 'apply' and len(args) == 2:
            raw = sys.stdin.read() if args[1] == '-' else open(args[1], encoding='utf-8').read()
            try:
                incoming = json.loads(raw)
            except ValueError as error:
                raise ConfigError('not valid JSON: %s' % error)
            if not isinstance(incoming, dict):
                raise ConfigError('expected a JSON object of {"key": value}')
            flat = flatten(incoming)
            skipped = sorted(key for key in flat if key in RETIRED_KEYS)   # a file saved before they were retired
            write(path, {key: check(key, value) for key, value in flat.items() if key not in RETIRED_KEYS})
            print('%d setting(s) written to %s' % (len(flat) - len(skipped), path))
            if skipped:
                print('skipped (retired, no longer settings): %s' % ', '.join(skipped))
            return 0
        raise ConfigError(__doc__.split('Layers,')[0].strip())
    except ConfigError as error:
        sys.stderr.write('%s\n' % error)
        return error.code
    except OSError as error:
        sys.stderr.write('%s\n' % error)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
