"""The podium configuration's layers on disk: where each file is, how a file is read, merged and written.

Split out of podium_config.py so no file passes 300 lines (rule #9); podium_config.py re-exports every name here.
Layers, lowest first: the shipped defaults < the user's file < the project's file (with its .claude/mode and
.claude/mode-model, which the file itself beats) < the session's own layer.
"""
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import fcntl
except ImportError:      # Windows: no advisory lock, the atomic replace below still never leaves a half-written file
    fcntl = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import podium_session as sessions  # noqa: E402
from podium_schema import DEFAULTS_FILE, RETIRED_KEYS, SCHEMA, SPECS  # noqa: E402

class ConfigError(Exception):
    """A usage error (exit 2) or an unreadable file (exit 1)."""

    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


class LockedError(ConfigError):
    """A locked setting asked to turn off (the secret scan, SAST): refused on a write, left out on a read."""


# The plugin was called `adyusuf` until 02/11/2026: its files and variables keep working (rule #4).
LEGACY = 'adyusuf'


def user_file():
    """PODIUM_CONFIG_USER (or the older ADYUSUF_CONFIG_USER), else ~/.claude/podium.json. A user who has only the older
    ~/.claude/adyusuf.json gets it copied to the new name once; if that copy fails, the older file is used."""
    chosen = os.environ.get('PODIUM_CONFIG_USER') or os.environ.get('ADYUSUF_CONFIG_USER')
    if chosen:
        return chosen
    home = os.path.join(os.path.expanduser('~'), '.claude')
    path, older = os.path.join(home, 'podium.json'), os.path.join(home, LEGACY + '.json')
    if not os.path.exists(path) and os.path.isfile(older):
        try:      # a temporary file renamed over: a copy cut short never leaves a half file under the new name
            fd, temp = tempfile.mkstemp(dir=home, prefix='.podium-', suffix='.tmp')
            os.close(fd)
            shutil.copyfile(older, temp)
            os.replace(temp, path)
        except OSError:
            with contextlib.suppress(OSError, UnboundLocalError):
                os.remove(temp)
            return older
    return path


def project_file():
    """The project's committed <root>/.claude/podium.json, or its older .claude/adyusuf.json while that is the only one."""
    try:
        top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        top = os.getcwd()
    path, older = os.path.join(top, '.claude', 'podium.json'), os.path.join(top, '.claude', LEGACY + '.json')
    return older if not os.path.exists(path) and os.path.isfile(older) else path


# The project's one-word files /podium:working-mode writes beside its podium.json, and the setting each one holds. The
# rules rank them above the configuration's own `mode` (CLAUDE.md #27, modes/README.md), so they are read as part of the
# project layer: one source for the mode (F-026, 14/11/2026). The project's podium.json beats them when it sets the key.
MODE_FILES = (('mode', 'mode'), ('mode-model', 'mode_model'))


def read_mode_files(folder):
    """({setting: value}, problems) from <folder>/mode and <folder>/mode-model. The first non-empty line is the value,
    checked like a `set` (a letter A-E in any case; a model of MODELS); anything else is a problem line and that file is
    ignored, while the other file and the project's podium.json still count. A missing file sets nothing.

    A valid letter with no usable mode-model beside it means every agent on its defined model (CLAUDE.md #27, "the letter
    alone"; modes/README.md): `mode_model` is then `keep`, so the user's or the shipped override never leaks under it."""
    values, problems = {}, []
    for name, key in MODE_FILES:
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8') as handle:
                word = next((line.strip() for line in handle if line.strip()), '')
            values[key] = check(key, word)
        except (OSError, ValueError, ConfigError) as error:
            problems.append('%s: %s (this file is ignored)' % (path, error))
    if 'mode' in values:
        values.setdefault('mode_model', 'keep')
    return values, problems


def flatten(tree, prefix=''):
    flat = {}
    for key, value in tree.items():
        name = prefix + key
        if isinstance(value, dict):
            flat.update(flatten(value, name + '.'))
        else:
            flat[name] = value
    return flat


def nest(flat):
    tree = {}
    for name in sorted(flat):
        node = tree
        parts = name.split('.')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = flat[name]
    return tree


def check(key, value, legacy=False):
    """The value as the schema wants it, or ConfigError (exit 2). `legacy`: also accept a value a file written before may
    hold (the spec's `legacy` list) - only when a file is READ; `set` and `apply` refuse it (qa 09/11/2026). An input
    alias (the spec's `aliases`, e.g. `force` for the stored `block`) is stored as the value it names."""
    spec = SPECS.get(key)
    if spec is None:
        raise ConfigError("unknown setting '%s' (see: podium_config.py schema)" % key)
    if spec['type'] == 'bool':
        text = str(value).strip().lower()
        if value is True or (not isinstance(value, bool) and text in ('true', 'yes', 'y', '1', 'on')):
            return True
        if value is False or (not isinstance(value, bool) and text in ('false', 'no', 'n', '0', 'off')):
            if spec.get('locked'):
                raise LockedError("'%s' is locked on and cannot be turned off: a security scan is never switched off (rule #19)" % key)
            return False
        raise ConfigError("'%s' is a yes/no setting, got %r" % (key, value))
    text = str(value).strip()
    text = spec.get('aliases', {}).get(text.lower(), text)
    for option in spec['options'] + (spec.get('legacy', []) if legacy else []):   # a legacy value is read, never offered (rule #4)
        if text.lower() == option.lower():
            return option
    raise ConfigError("'%s' must be one of %s, got %r" % (key, '/'.join(spec['options']), value))


def read_layer(path, keep_unknown=False):
    """(flat values, problem). A missing file is an empty layer; an unreadable or invalid one is reported.

    A key this schema does not know was written by a NEWER plugin (forward compatibility, rule #11): it is left out of
    the values, never a problem, so one new key does not throw away the whole layer - an older copy once read a user's
    file holding `coverage_before_push.dev` as empty and answered push.prod = yes against the user's no (found by QA
    30/10/2026). `keep_unknown` hands such keys back unchecked, so a write keeps what the newer plugin wrote."""
    if not os.path.exists(path):
        return {}, None
    try:
        with open(path, encoding='utf-8') as handle:
            tree = json.load(handle)
        if not isinstance(tree, dict):
            raise ValueError('the top level is not an object')
        flat = flatten(tree)
        values = {}
        for key, value in flat.items():
            if key in RETIRED_KEYS:
                continue
            if key not in SPECS:
                if keep_unknown:
                    values[key] = value
                continue
            if SPECS[key].get('locked'):
                # A locked step written off by hand (or by an older copy) is left out, so it stays on and the rest of
                # the layer still counts; refusing the whole file would throw away the user's other settings. Any other
                # bad value still makes the layer a problem, as for every key.
                with contextlib.suppress(LockedError):
                    values[key] = check(key, value, legacy=True)
                continue
            values[key] = check(key, value, legacy=True)
        return values, None
    except (OSError, ValueError, ConfigError) as error:
        return {}, '%s: %s' % (path, error)


def load(user_path=None, session=None, project=True):
    """(effective {key: (value, source)}, problems [str]). `user_path` replaces the user's file (the installer's --home);
    `session` adds that session's layer on top (an unusable id adds nothing). `project=False` leaves the project's layer out."""
    problems = []
    defaults, problem = read_layer(DEFAULTS_FILE)
    if problem:
        problems.append(problem)
    # A setting the shipped file does not hold takes its schema default (the gate steps: on).
    effective = {spec['key']: (defaults.get(spec['key'], spec.get('default')), 'default') for spec in SCHEMA}
    layers = [('user', user_path or user_file())] + ([('project', project_file())] if project else [])
    if sessions.valid(session):
        layers.append(('session', sessions.session_file(session)))
    for source, path in layers:
        values, problem = read_layer(path)
        if problem:
            # One bad value drops the whole file (fail-closed: never half a project file), so the problem says so (F-028).
            problems.append('%s - the whole file is ignored, the layers below it apply' % problem)
        if source == 'project':
            files, trouble = read_mode_files(os.path.dirname(path))
            problems.extend(trouble)
            values = dict(files, **values)
        for key, value in values.items():
            effective[key] = (value, source)
    return effective, problems


@contextlib.contextmanager
def locked(path):
    """One writer at a time per configuration file (clicks in the rail boxes arrive in quick succession). The lock file
    lives in the temp folder, keyed by the path, so no `.lock` lands in ~/.claude or in a project's committed `.claude/`."""
    name = 'podium-config-%s.lock' % hashlib.sha1(os.path.abspath(path).encode('utf-8')).hexdigest()[:16]
    with open(os.path.join(tempfile.gettempdir(), name), 'a') as handle:
        if fcntl:
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield                                    # closing the handle releases the lock


def write_layer(path, changes, removals=()):
    """Merge `changes` into the layer's file and write it back. Refuses to overwrite an unreadable file. The read, the
    change and the write happen under a lock, and the file is replaced atomically: a reader never sees it half-written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with locked(path):
        current, problem = read_layer(path, keep_unknown=True)
        if problem:
            raise ConfigError('refusing to overwrite an unreadable configuration file - ' + problem, 1)
        current.update(changes)
        # e.g. {"push": true} written by hand where the group push.* lives: nest() cannot hold both, and an unset of
        # push.prod there would rewrite a file that is wrong about that group (F-027): refused, the file left as it was.
        named = set(current) | set(removals)
        groups = sorted({other for other in current for key in named if key.startswith(other + '.')})
        for key in removals:
            current.pop(key, None)
        if groups:
            raise ConfigError("refusing to write %s: it would hold '%s' both as a single value and as a group of settings "
                              "- fix or remove it by hand" % (path, "', '".join(groups)), 1)
        temp = '%s.%d.tmp' % (path, os.getpid())
        try:
            with open(temp, 'w', encoding='utf-8') as handle:
                json.dump(nest(current), handle, indent=2)
                handle.write('\n')
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.remove(temp)
