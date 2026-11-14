# Test inventory — Status box and status engine (`pane Status box · scripts/podium_status.py`)

> Writes and shows the session's steps, subagent rows and spend; the hooks keep it current.
> Files: `hooks/status.ts`, `register.tsx` (status paths); `scripts/podium_status.py`, `podium_status_rows.py`, `podium_status_hooks.py`, `podium_status_agents.py`, `podium_budget.py`; `step-stats.py` + `step_stats_*.py`
>
> Audited: 14/11/2026 · branch `docs/test-inventory` · phase 1

## 1. Tests on this surface — by the numbers

py = `scripts/tests` (pytest) · deno = `hooks/*.test.ts` · engine = `hooks/register.test.tsx` (`claude plugin test`) · ci = `.github/workflows`. Web e2e, Android, iOS and Maestro do not exist in this repository: `—`.

| Layer | Files | Tests |
|---|---|---|
| py | `test_podium_status.py`, `_agents`, `_steps`, `test_podium_budget.py`, `test_step_stats_core/report/roles.py` | 116 (`grep -c "def test_"`) |
| deno | `status.test.ts`, `info.test.ts` (status part) | 14 + 1 (2 of the 14 fail: shim lacks `.not`, known) |
| engine | `register.test.tsx` | 0 status assertions |

**Measured coverage:** `scripts/podium_status.py` 92% · `scripts/podium_status_rows.py` 99% · `scripts/podium_status_agents.py` 96% · `scripts/podium_budget.py` 90% · `scripts/step-stats.py` 37% · `hooks/status.ts` not measured (the TS suite failed type-check: F-042) (command: `bash scripts/coverage.sh`, 14/11/2026).

## 2. Use cases and what is tested

`✅` tested · `◐` partly · `❌` not tested · `—` not implemented. Built from the code; the layer that tests each is named in the cell.

| # | Use case | Tested |
|---|---|---|
| 1 | Hooks: session, prompt, stop, subagent, tool, subagent-stop | ✅ py |
| 2 | waitAfterInterrupt after an aborted turn | ❌ (F-037) |
| 3 | CLI now/next/row/step/drop/rename/clear/show | ✅ py |
| 4 | A step with an unparseable percent | ❌ (F-006) |
| 5 | Persistence: lock, atomic replace, corrupt file, prune | ✅ py |
| 6 | Budget line | ✅ py (no size cap: F-039) |
| 7 | Pane read path and drawing | ✅ deno |
| 8 | readStatus, queue, poll, onTurnComplete | ❌ (F-029) |
| 9 | Python/TS parity on caps and percent | ◐ (F-038) |
| 10 | step-stats CLI | ◐ helpers only (F-040) |

## 3. What is wrong — defects and unhandled cases

| Id | Priority | Class | Finding | Evidence |
|---|---|---|---|---|
| [F-004](findings.md) | 🟡 | Unhandled case | `steps.enforce=block` judges only Edit/Write/NotebookEdit and a plain `git commit`: `if …; then git commit`, `(git commit)`, `env A=1 git commit`, and Bash file writes (`sed -i`, `>`, `tee`) all pass. | `scripts/podium_status_hooks.py:62` (COMMIT), `:106-107`; probe COMMIT.search → no match |
| [F-005](findings.md) | 🟡 | Unhandled case | The steps guard opens on a bad payload: unparseable JSON, a non-object `tool_input`, a missing or invalid `session_id` all exit 0 under `block`. | `scripts/podium_status_hooks.py:110,128,191-192`; probe `echo garbage \| podium_status.py hook guard` → exit 0 |
| [F-006](findings.md) | 🟡 | Defect | A step written with a non-numeric percent (`"3 of 8"`, `n/a`) is stored with an empty percent, and the guard then treats the running step as not open: every edit is refused although the Status box shows a running step. | `scripts/podium_status_rows.py:33-36`, `scripts/podium_status_hooks.py:77`; probe step "3 of 8" → exit 0, then guard Edit → exit 2 "no step … is open" |
| [F-037](findings.md) | 🟢 | Unhandled case | After an interrupted turn the pane runs `python3 "" hook stop` when no plugin script is found and does not check the exit code, so the Status box can stay "running" with no log. | `hooks/register.tsx:235-238`, `hooks/status.ts:38-39` |
| [F-039](findings.md) | 🟢 | Unhandled case | The budget line reads whole transcripts with no size cap on every prompt, stop and subagent stop (the agent counter caps at 64 MB); no hook in hooks.json has a timeout. | `scripts/podium_budget.py:31-40`; `grep -c timeout hooks/hooks.json` → 0 |
| [F-042](findings.md) | 🟡 | Defect | The coverage step is red for the whole repository: `coverage.sh` type-checks the TypeScript tests, the 2 known `.not` failures in `hooks/status.test.ts` fail that check, so TypeScript coverage is "not a measurement" and `coverage.sh` exits 1 although Python (90 %) and shell (81 %) pass. Every gate with coverage on is therefore red. | `bash scripts/coverage.sh` → "TS2339 Property 'not' does not exist", "✗ the tests are red", exit 1 (14/11/2026); `scripts/ts-shim/claude-code-testing.ts:6-10` |

## 4. What is missing — test gaps

| Id | Priority | Gap | Evidence | Phase 2 |
|---|---|---|---|---|
| [F-029](findings.md) | 🟡 | The mod's data paths in `register.tsx` (setSetting, the click queue, refreshSettings, refreshPromotion, readStatus, the poll, waitAfterInterrupt) have no test: the engine test only mounts the pane, and its comment says they are exercised by hand. | `hooks/register.test.tsx:3-6`, `hooks/register.tsx:54-143,156-253` | pending |
| [F-040](findings.md) | 🟢 | step-stats CLI paths (`--days`, `--write`, `compare_cuts`, `collect`, `report`) have no test; `--days abc` raises; the `--write` file handle is not closed; the sanitiser still lists retired names. | `scripts/step-stats.py:164,245`, `scripts/step_stats_sanitiser.py:17` | pending |

**Proposed phase-2 tests** (written only after approval; a defect's regression test is written with its approved fix):

- py: an unparseable percent is refused or still counts as open; guard after it (F-006, 2 tests)
- py: an oversized transcript gives no figure (F-039)
- py: step-stats `--days abc` exits 2; a bad cuts line is skipped (F-040)
- deno: percent over 100 clamped; 50-row trim order (F-038)
- engine/deno: aborted turn writes waiting; no script → no run (F-037); readStatus keeps the table on an error (F-029)

## 5. Not counted as gaps

- Parity: Windows: no lock (documented in the script header).
- E2E backlog: none (no running application; e2e is out of scope for this repository, `scripts/merge-gate.conf`).

## 6. Run results (phase 3 ⇄ 4)

Not run yet.
