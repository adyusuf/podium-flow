#!/usr/bin/env bash
# The hook that runs the CLAUDE.md size ratchet automatically. It is bound to TWO
# events at once:
#
#   PostToolUse (Edit|Write) : immediately after the edit, for instant feedback
#   Stop                     : at the end of the turn, a METHOD-AGNOSTIC safety net
#
# ⚠️ WHY THE STOP EVENT IS ESSENTIAL: the PostToolUse matcher looks at the TOOL
# NAME. If Claude edits a CLAUDE.md through `Bash` (sed / a python heredoc / cat >)
# neither Edit nor Write fires and the hook stays SILENT. This is not theoretical:
# the very session in which this hook was installed made all of its CLAUDE.md
# edits through Bash — the hook would not have fired even once on the turn that
# created it. The Stop event looks at the whole repository at the end of the turn
# and does not care how the edit was made.
#
# ⚠️ SILENT WHEN GREEN: printing "within budget" on every turn is noise, and noise
# teaches people not to read. It speaks only when something EXCEEDS its ceiling or
# has NO BUDGET.
#
# ⚠️ This is NOT a release gate, it is a behavioural warning; the exit code is
# always 0. In a project where it is a real merge gate, a COPY of the script lives
# in the repository and CI runs that (see the podium plugin's scripts/README.md).
# Keep the distinction.
#
# It ships with the podium plugin (hooks/hooks.json runs it as
# "${CLAUDE_PLUGIN_ROOT}/scripts/md-hook.sh") and finds its siblings RELATIVE TO
# ITSELF: the plugin's scripts/ is the canonical set. `cd` + `pwd` keeps the path
# it was invoked with, so an old install that still calls it through the
# ~/.claude/scripts directory symlink finds the same siblings through that link.
set -uo pipefail

# Every command sits on its own line and its output is assigned first: the plugin directory's validator reads each
# command on its own and refuses a script whose commands sit inside quoted strings (02/11/2026).
here=$(dirname "${BASH_SOURCE[0]}")
here=$(cd "$here" && pwd)

input=$(cat 2>/dev/null)

# PostToolUse supplies a file path; the Stop event does not.
path=$(python3 "$here/md_hook_path.py" <<<"$input" 2>/dev/null)

if [ -n "$path" ]; then
  # Tool-based call: only CLAUDE.md is of interest.
  name=$(basename "$path")
  [ "$name" = "CLAUDE.md" ] || exit 0
  start=$(dirname "$path")
else
  # Stop event: look at the repository of the current working directory.
  start=$PWD
fi

root=$(git -C "$start" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -n "$root" ] || exit 0

export MD_ROOT="$root"
output=$(bash "$here/md-size-gate.sh" --hook 2>&1)

# If no budget is installed, stay QUIET on the Stop event (suggesting an install
# on every turn is noise); say it once if a CLAUDE.md was explicitly edited.
if printf '%s' "$output" | grep -qi 'no CLAUDE.md budget is installed'; then
  [ -n "$path" ] && printf '%s\n' "$output"
  exit 0
fi

if printf '%s' "$output" | grep -qi 'CEILING EXCEEDED\|NO BUDGET\|FILE MISSING'; then
  echo "⚠️ A CLAUDE.md budget was exceeded — a new permanent decision belongs in docs/<topic>.md, not in the root file:"
  printf '%s\n' "$output" | grep -Ei 'CEILING EXCEEDED|NO BUDGET|FILE MISSING'
  echo "   If you simplified it:  bash scripts/md-size-gate.sh --update"
fi

# ── Twin drift ───────────────────────────────────────────────────────────────
# Every script a project COPIES is a deliberate TWIN: the canonical copy lives in
# the podium plugin's scripts/ (this file's own directory), and every project takes a COPY into its own scripts/ and
# commits it (a project's gate cannot depend on a path outside the repository).
# Where there are twins there must also be a DRIFT TEST — this repository does
# exactly that for its other twins. Drift did happen once: the canonical copy was
# updated, the project copy stayed behind, and it was only noticed by comparing
# them by hand.
# The list lives in ONE file (twins.txt), shared with twin-drift.sh: two lists that disagree would mean
# a script is checked in one place and not the other.
TWINS_FILE="${TWINS_FILE:-$here/twins.txt}"
TWINS=$(grep -vE '^[[:space:]]*(#|$)' "$TWINS_FILE" 2>/dev/null | tr '\n' ' ')
[ -n "$TWINS" ] || echo "⚠️ The twin list is missing or empty ($TWINS_FILE): copied scripts are NOT being checked for drift."
drifted=""
# The configuration repository IS the canonical set: comparing one of its worktrees
# with the installed plugin's copy would report every not-yet-promoted change as drift.
if ! { [ -f "$root/standards/README.md" ] && [ -d "$root/modes" ]; }; then
  for tool in $TWINS; do
    [ -f "$root/scripts/$tool" ] || continue          # this project did not copy it
    [ -f "$here/$tool" ] || continue                  # no canonical copy to compare with
    cmp -s "$root/scripts/$tool" "$here/$tool" || drifted="$drifted $tool"
  done
fi
if [ -n "$drifted" ]; then
  echo "⚠️ The copied scripts have DRIFTED from the canonical copy:$drifted"
  echo "   Canonical: the podium plugin's scripts/ ($here/)  ·  This project: $root/scripts/"
  echo "   Which one is current? Compare first, then bring BOTH into line:"
  echo "   diff \"$here/<tool>\" scripts/<tool>"
fi
exit 0
