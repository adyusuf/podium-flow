---
name: working-mode
description: Shows or changes the operating mode (A/B/C/D/E) for this project, optionally with a model that replaces Opus for the Opus agents ("C sonnet"). The mode determines agent usage, review and the approval policy, and so how fast the session spends tokens. Use it when the user says "/podium:working-mode", "change the mode", "which mode are we in", "work as a full team", or "work without agents".
---

# Working mode

## Why this exists

Writing code with agentic AI from Claude Desktop means working with **subagents only**:
Desktop cannot start an agent team, so this skill makes the session itself the
orchestrator and runs subagents in a controlled, synchronous way. And once you work on
more than one project at a time, tokens run out — so the mode is the dial for **how fast
a session spends them**. Pick the smallest mode the work needs:

| Mode | Who works | Agents |
|---|---|---|
| A | The session alone, no agents | 0 |
| B | Selective — `analyst`, `test-writer`, `doc-writer` | 3 roles |
| C | Full team (default) | 9 roles |
| D | Wide team | 14 roles |
| E | Fan-out through `Workflow` | the 14 roles, in parallel |

The work is **audited** in every mode: a producing role closes with an evidence block,
and the auditor checks it and sends gaps back (global #28). In C/D/E the auditor is the
`qa` agent (the session verifies its critical findings); in A/B it is the session itself.

Contributions are welcome: https://github.com/adyusuf/podium-flow

## 0. At session start - no question

A session does not ask the mode (user decision 17/10/2026): the read order of §1 decides, and the SessionStart hook has
already printed the effective values. Apply nothing at start. The defaults themselves are changed with `/podium:config`.
Rules: `${CLAUDE_PLUGIN_ROOT}/modes/README.md` › *Session start*.

## 1. Read the current mode

Priority order: **the session's choice** → the project's `.claude/mode` → the configuration (`mode`, default C).
One script answers it: `podium_config.py` reads the session layer, then the project's `.claude/podium.json` with its
`.claude/mode` and `.claude/mode-model` (the project's `podium.json` beats them when it sets the key), then the user's
file and the shipped defaults.

```bash
SID="<this session's id: the 'this session is <id>' line of the start-of-session block; empty if there is none>"
cfg="${CLAUDE_PLUGIN_ROOT}/scripts/podium_config.py"
echo "mode: $(python3 "$cfg" get mode ${SID:+--session "$SID"})"
echo "opus agents run on: $(python3 "$cfg" get mode_model ${SID:+--session "$SID"})"   # keep = their defined model
```

`show --json` (same `--session`) names the layer each value came from (`session`, `project`, `user`, `default`). A
problem line on stderr (`! ...`) names a file that was ignored: a `.claude/mode` that is not one letter A-E, a
`.claude/mode-model` that is not one of keep/sonnet/haiku/fable, or a settings file with a bad value. Say it to the user.

If none of them sets the mode the configuration's mode applies (default **C**, `podium:config`); its agents are approved
by the default itself. Propose a lower or higher mode in one line only if the work clearly deserves it - never switch on
your own (README › "If no mode is given").

⚠️ A mode chosen with `--once` is written **to this session's layer** (`set --session <id>`), not to `.claude/mode`.
Reason: if "apply this for this session only" relies on memory, it is **forgotten** after context compaction and the
project file's mode silently takes over again. The session layer lives as long as the session id (a resumed session
keeps it, `/clear` starts a new one) - exactly the lifetime required.

History: before 14/11/2026 `--once` wrote `$S/mode` and `$S/mode-model` in the scratchpad. Such a file is never
written again and no script reads it; it stays as a read-only record. A session that still has one and wants that
choice kept runs §4 with `--once` once.

## 2. Load the mode definitions

`${CLAUDE_PLUGIN_ROOT}/modes/README.md` is the matrix (single source). Read the active mode's
file: `${CLAUDE_PLUGIN_ROOT}/modes/<LETTER>-*.md` (each of the five letters resolves to one
file). **Read only the active mode's file** — reading all five burns context for
nothing. ⚠️ **X/Y/Z are archived** (`modes/archive/README.md`) and are never
offered as a mode.

## 3. If called without an argument

Show the current mode, what it means and the other options **briefly**: letter +
name + agent set + who reviews + cost multiplier. Do not paste the whole matrix;
5-6 lines are enough (A-E).

## 4. If a letter is given (`/podium:working-mode B`, `/podium:working-mode C sonnet`)

0. Split the argument: the letter, an optional **model word**, an optional `--once`/`--tek`.
   The model word must be `sonnet` · `haiku` · `fable` · `opus`; anything else is
   rejected with that list and **nothing is written**. `opus` is the same as no model
   word.
1. Validate the letter (**A/B/C/D/E**). ⚠️ **D and E swapped places**: D is now the
   14-role wide team and E is fan-out (`Workflow`). Correct any "D = fan-out"
   expectation carried over from older sessions. Reject an invalid letter and
   show the list.
2. If `--once` was not given, write the **single letter** to `.claude/mode` at the
   repository root:
   ```bash
   root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)" && mkdir -p "$root/.claude" && printf '%s\n' "B" > "$root/.claude/mode" && echo "written: $root/.claude/mode"
   ```
   ⚠️ The fallback is mandatory: in a directory that is not a git repository
   `git rev-parse` exits **128** and breaks the `&&` chain, so the file is never
   written. The read command used to have a fallback while the write did not:
   the user was told "saved permanently" when nothing had been saved. **If the
   write fails, say so** — never confirm it.
   If `--once` was given, do **not** write `.claude/mode`; write this session's layer instead (it beats the project
   file in the priority order of §1). The session id is on the `this session is <id>` line; without one `--once`
   cannot be kept - say so and write nothing:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/podium_config.py" set --session "$SID" mode B
   ```
2a. Write or clear the model override **in the same layer** as the letter. Project (`$root/.claude`):
   ```bash
   dir="$root/.claude"
   if [ -n "$model" ] && [ "$model" != opus ]; then printf '%s\n' "$model" > "$dir/mode-model"; else rm -f "$dir/mode-model"; fi
   ```
   Session (`--once`): `opus` or no model word is `keep` (the defined models):
   ```bash
   m="$model"; [ "$m" = opus ] && m=""
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/podium_config.py" set --session "$SID" mode_model "${m:-keep}"
   ```
   ⚠️ The letter alone **clears** the override — that is how the user returns to the
   defined models. Never keep an old `mode-model` next to a newly written letter.
   `.claude/mode` and `.claude/mode-model` stay a single word (the settings engine reads the first non-empty line;
   anything else is reported and ignored).
3. Read the new mode's file and **follow its rules from that point on**.
4. Confirm to the user: old mode → new mode, and what changed (agent set, who
   reviews, approval policy, expected multiplier) **and the model line**: which
   agents are Opus by definition and what they run on now. 4-6 lines.
5. **From then on**, every `Agent` call (and every `Workflow` `agent()`) passes `model: "<runs_on>"` for
   its role as `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/podium_config.py agents --json --session "$SID"` lists it (without
   a session id, leave `--session` out): the mode's Opus
   override, or the model the user set for that one agent (`/podium:config`); an agent whose `runs_on` is its
   defined model gets no override, and a role that is not listed is not called. Report the model that actually ran. A role agent is always
   called by its plugin name, `subagent_type: "podium:<role>"`; a bare `<role>` is not found.

## Permanent rules

- `.claude/mode` **is committed** — it carries the project default across team
  members and sessions. Use `--once` for a personal, temporary preference.
- **In modes B/C/D/E** choosing the mode **is** the approval for that agent set
  (#27); no separate question before a call. At the end of the turn the number of
  agents that ran and the estimated cost are **reported**.
- **In mode A** no agent is ever invoked; if an agent is needed, propose changing
  the mode instead of starting one.
- The mode **never** loosens any of these: approval for irreversible work, the
  promotions over a red or incomplete gate, the completeness check before
  "done", secrets staying out of the repository.
- `.claude/mode-model` is committed with `.claude/mode` (same narrow gitignore
  exception); with no override the file does not exist.
- A mode change is **not retroactive** — work done in earlier turns is not
  re-evaluated.
