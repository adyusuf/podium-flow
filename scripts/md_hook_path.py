"""md-hook.sh's payload reader: prints the edited file's path from a hook payload on stdin, or nothing.

PostToolUse supplies `tool_input.file_path` (or `path`); the Stop event supplies neither. A payload that is not JSON
prints nothing, so md-hook.sh treats it as the Stop event. Kept out of md-hook.sh so the plugin directory's validator
can read every command of that script on its own (02/11/2026).
"""
import json
import sys


def edited_path(text):
    try:
        payload = json.loads(text)
    except ValueError:
        return ''
    given = payload.get('tool_input') if isinstance(payload, dict) else None
    if not isinstance(given, dict):
        return ''
    return str(given.get('file_path') or given.get('path') or '')


if __name__ == '__main__':
    print(edited_path(sys.stdin.read()))
