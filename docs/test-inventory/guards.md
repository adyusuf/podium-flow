# Test inventory — Guards (`PreToolUse hooks: guard-destructive.sh, podium_status.py hook guard`)

> Blocks irreversible shell commands, and holds code edits and commits until the Status box has steps (`steps.enforce=block`).
> Files: `scripts/guard-destructive.sh`, `scripts/guard-inspect.py`; `scripts/podium_status.py` `hook guard` → `scripts/podium_status_hooks.py` (`blocked`, `bookkeeping`, `COMMIT`); wired in `hooks/hooks.json`
>
> Audited: 14/11/2026 · branch `docs/test-inventory` · phase 1

## 1. Tests on this surface — by the numbers

py = `scripts/tests` (pytest) · deno = `hooks/*.test.ts` · engine = `hooks/register.test.tsx` (`claude plugin test`) · ci = `.github/workflows`. Web e2e, Android, iOS and Maestro do not exist in this repository: `—`.

| Layer | Files | Tests |
|---|---|---|
| py | `test_guard_destructive.py` (through the real wrapper), `test_guard_inspect.py`, `test_podium_status_steps.py` | 44 + 14 (`pytest --collect-only -q`, `grep -c "def test_"`) |

**Measured coverage:** `scripts/guard-inspect.py` 100% · `scripts/podium_status_hooks.py` 97% · `scripts/guard-destructive.sh` 63.6% (command: `bash scripts/coverage.sh`, 14/11/2026).

## 2. Use cases and what is tested

`✅` tested · `◐` partly · `❌` not tested · `—` not implemented. Built from the code; the layer that tests each is named in the cell.

| # | Use case | Tested |
|---|---|---|
| 1 | Forced push, push to main, `--no-verify` | ◐ only the listed spellings; bypasses untested (F-001) |
| 2 | DROP/TRUNCATE; recursive delete of a root | ◐ long options and quoted $HOME untested |
| 3 | Heredoc bodies stripped for the git rules | ✅ (here-string mishandled: F-002) |
| 4 | Fail closed: grep, inspector, Python missing or crashing | ✅ |
| 5 | Symlinked install; JSON vs raw payload | ✅ |
| 6 | Steps guard on Edit/Write/NotebookEdit and `git commit` | ◐ other commit spellings and Bash writes (F-004) |
| 7 | Bookkeeping exemptions | ◐ sibling prefixes, temp folders (F-003) |
| 8 | Bad payload / missing session under `block` | ◐ asserted only under `remind` (F-005) |
| 9 | Hook command lines exactly as in hooks.json | ◐ registration only |

## 3. What is wrong — defects and unhandled cases

| Id | Priority | Class | Finding | Evidence |
|---|---|---|---|---|
| [F-001](findings.md) | 🔴 | Defect | The destructive-command guard lets through forced and destructive pushes it is meant to block: `git push -fu`, a `+refspec` push, `git -C <dir> push --force`, `--mirror`, `--delete`, a push to `refs/heads/main`, `git commit -n`, `rm --recursive --force /`, `rm -rf "$HOME"`. | `scripts/guard-inspect.py:50-58`; probe `command_of`+`verdict` and `echo {..git push -fu origin dev..} \| bash scripts/guard-destructive.sh` → exit 0 |
| [F-002](findings.md) | 🔴 | Defect | A here-string (`<<<word`) is taken for a heredoc start, so every later line is stripped before the git rules run: `cat <<<foo` then `git push --force` on the next line passes. | `scripts/guard-inspect.py:42` regex `<<-?`; probe → allowed |
| [F-003](findings.md) | 🟡 | Defect | The steps-first guard counts any path that only starts with a bookkeeping folder as bookkeeping (`~/.claude/plans-x/…`, `~/.claude/projectsEVIL/…`), and every file under `/tmp`, `/private/tmp` or `/var/folders`, so code there is never held for steps. | `scripts/podium_status_hooks.py:57-61,105`; probe `bookkeeping()` → True for all four |
| [F-004](findings.md) | 🟡 | Unhandled case | `steps.enforce=block` judges only Edit/Write/NotebookEdit and a plain `git commit`: `if …; then git commit`, `(git commit)`, `env A=1 git commit`, and Bash file writes (`sed -i`, `>`, `tee`) all pass. | `scripts/podium_status_hooks.py:62` (COMMIT), `:106-107`; probe COMMIT.search → no match |
| [F-005](findings.md) | 🟡 | Unhandled case | The steps guard opens on a bad payload: unparseable JSON, a non-object `tool_input`, a missing or invalid `session_id` all exit 0 under `block`. | `scripts/podium_status_hooks.py:110,128,191-192`; probe `echo garbage \| podium_status.py hook guard` → exit 0 |
| [F-006](findings.md) | 🟡 | Defect | A step written with a non-numeric percent (`"3 of 8"`, `n/a`) is stored with an empty percent, and the guard then treats the running step as not open: every edit is refused although the Status box shows a running step. | `scripts/podium_status_rows.py:33-36`, `scripts/podium_status_hooks.py:77`; probe step "3 of 8" → exit 0, then guard Edit → exit 2 "no step … is open" |
| [F-041](findings.md) | 🟢 | Unhandled case | The rm/DROP rules are checked inside heredoc bodies, so a heredoc that only writes text quoting such a command is blocked (hit while writing this audit). Safe direction, a usability cost. | `scripts/guard-inspect.py:63-67`; blocked hook call 14/11/2026 |

## 4. What is missing — test gaps

| Id | Priority | Gap | Evidence | Phase 2 |
|---|---|---|---|---|
| — | | the gaps of this surface are the tests attached to its defects (below) | | |

**Proposed phase-2 tests** (written only after approval; a defect's regression test is written with its approved fix):

- py: bypass table for F-001, through `verdict` and through the wrapper (one parametrised test each)
- py: here-string is not a heredoc (F-002)
- py: sibling-prefix path is code work; temp-folder repo (after the decision) (F-003)
- py: commit spellings and Bash writes pinned to the decided scope (F-004)
- py: bad payload under `block` (F-005)
- py: a malformed percent (F-006, also Status)

## 5. Not counted as gaps

- Parity: none.
- E2E backlog: none (no running application; e2e is out of scope for this repository, `scripts/merge-gate.conf`).

## 6. Run results (phase 3 ⇄ 4)

Not run yet.
