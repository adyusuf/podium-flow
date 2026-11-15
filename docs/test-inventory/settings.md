# Test inventory — Settings box and settings engine (`pane Settings box · scripts/podium_config.py`)

> Shows and changes the podium settings per session, user and project; tells a running session about changes.
> Files: `hooks/boxes.ts`, `rows.ts`, `choose.ts`, `gatesteps.ts`, `help.ts`, `controls.ts`, `notices.ts`, `register.tsx` (settings paths); `scripts/podium_config.py`, `podium_layers.py`, `podium_schema.py`, `podium_session.py`; `defaults/podium.json`; `skills/config`, `skills/working-mode`
>
> Audited: 14/11/2026 · branch `docs/test-inventory` · phase 1

## 1. Tests on this surface — by the numbers

py = `scripts/tests` (pytest) · deno = `hooks/*.test.ts` · engine = `hooks/register.test.tsx` (`claude plugin test`) · ci = `.github/workflows`. Web e2e, Android, iOS and Maestro do not exist in this repository: `—`.

| Layer | Files | Tests |
|---|---|---|
| py | `test_podium_config.py`, `test_podium_session.py`, `test_podium_legacy_names.py`, `test_podium_gate_steps.py`, `test_panel_discover.py` | 102 (`pytest --collect-only -q`) |
| deno | `boxes`, `nocode`, `info`, `help`, `gatesteps`, `notices`, `choose` `.test.ts` | 82 (`grep -cE "^test\("`; shared with Agents and Promotion) |
| engine | `register.test.tsx` | 2 bodies × 2 surfaces; mount only |

**Measured coverage:** `scripts/podium_config.py` 90% · `scripts/podium_layers.py` 96% · `scripts/podium_schema.py` 100% · `scripts/podium_session.py` 93% · `hooks/boxes.ts` not measured (the TS suite failed type-check: F-042) · `hooks/choose.ts` not measured (the TS suite failed type-check: F-042) · `hooks/gatesteps.ts` not measured (the TS suite failed type-check: F-042) · `hooks/notices.ts` not measured (the TS suite failed type-check: F-042) · `hooks/rows.ts` not measured (the TS suite failed type-check: F-042) (command: `bash scripts/coverage.sh`, 14/11/2026).

## 2. Use cases and what is tested

`✅` tested · `◐` partly · `❌` not tested · `—` not implemented. Built from the code; the layer that tests each is named in the cell.

| # | Use case | Tested |
|---|---|---|
| 1 | show/get/schema; layer precedence | ✅ py |
| 2 | set: parse, aliases, locked refusal, unknown key | ◐ py: no direct `set force` → block |
| 3 | unset, apply, reset-agents | ◐ py: apply from stdin/missing file |
| 4 | write_layer: lock, atomic replace, unreadable file refused | ◐ py: scalar-vs-group (F-027) |
| 5 | Backward compatibility (adyusuf, retired keys, legacy budget, `long`) | ✅ py, deno |
| 6 | context and notify | ✅ py (long/non-ASCII id: F-032) |
| 7 | A bad layer | ◐ dropped silently (F-028) |
| 8 | The settings table, tabs, no-code rows, legacy option | ✅ deno |
| 9 | A press: click queue → setSetting → toast/refresh | ◐ deno: mapping only; ❌ the glue (F-029, F-030) |
| 10 | refreshSettings and change warnings | ◐ deno: warnings only |
| 11 | Mode files `.claude/mode` | ❌ not implemented (F-026) |

## 3. What is wrong — defects and unhandled cases

| Id | Priority | Class | Finding | Evidence |
|---|---|---|---|---|
| [F-026](findings.md) | 🟡 | Unhandled case | No script reads `.claude/mode` or the session scratchpad mode, which the rules and the working-mode skill rank above the config `mode`; the session-start "mode X" line, `agents` and the Agents box use the config key alone and can disagree with the mode in force. | `scripts/podium_config.py:92`, `scripts/podium_schema.py:153`; `grep -rln ".claude/mode" scripts hooks` → only a comment |
| [F-027](findings.md) | 🟡 | Unhandled case | A hand-edited layer with a scalar where a group is expected (`{"push": true}`) makes `set push.prod no` end in a Python traceback instead of the documented exit 0/1/2. | `scripts/podium_layers.py:82-90,190-199`; probe → `TypeError: 'bool' object does not support item assignment` |
| [F-028](findings.md) | 🟡 | Defect | One bad value drops a whole layer silently on `get` and in the pane: a project file with `push.prod: "maybe"` and `mode: B` loses its `mode` too, and `get push.prod` answers the user layer's `yes` with no warning (only `context` prints a `!` line). | `scripts/podium_layers.py:149-150`, `scripts/podium_config.py:250-255`; probe → `get push.prod` = yes, `get mode` = C |
| [F-030](findings.md) | 🟡 | Unhandled case | A rejected settings click is swallowed: `click()` ends in `.catch(() => undefined)`, so a failed spawn gives no toast and no log, and the press does nothing. | `hooks/register.tsx:208-210` |
| [F-031](findings.md) | 🟢 | Unhandled case | A gate-step press writes two layers, each followed by its own refresh, so the same change can be announced twice (extends the known unserialised refreshSettings). | `hooks/gatesteps.ts:69-72`, `hooks/register.tsx:136` |
| [F-042](findings.md) | 🟡 | Defect | The coverage step is red for the whole repository: `coverage.sh` type-checks the TypeScript tests, the 2 known `.not` failures in `hooks/status.test.ts` fail that check, so TypeScript coverage is "not a measurement" and `coverage.sh` exits 1 although Python (90 %) and shell (81 %) pass. Every gate with coverage on is therefore red. | `bash scripts/coverage.sh` → "TS2339 Property 'not' does not exist", "✗ the tests are red", exit 1 (14/11/2026); `scripts/ts-shim/claude-code-testing.ts:6-10` |

## 4. What is missing — test gaps

| Id | Priority | Gap | Evidence | Phase 2 |
|---|---|---|---|---|
| [F-029](findings.md) | 🟡 | The mod's data paths in `register.tsx` (setSetting, the click queue, refreshSettings, refreshPromotion, readStatus, the poll, waitAfterInterrupt) have no test: the engine test only mounts the pane, and its comment says they are exercised by hand. | `hooks/register.test.tsx:3-6`, `hooks/register.tsx:54-143,156-253` | pending |
| [F-032](findings.md) | 🟢 | `notify` does not use `sessions.valid` (a 300-character id silently never gets a seen-file); its tests are duplicated in two files; the seen-file is not written atomically; `reset-agents` calls `load()` and drops the result. | `scripts/podium_config.py:140,150-157,231` | pending |

**Proposed phase-2 tests** (written only after approval; a defect's regression test is written with its approved fix):

- py: scalar where a group is expected → exit 1 (F-027)
- py: `get` warns when a layer was dropped (F-028)
- py: `set steps.enforce force` stores block; apply from stdin and a missing file; unset on project/user
- py: notify ignores an over-long id; two notifies say the change once (F-032)
- py: mode files and the config mode (after the F-026 decision)
- deno (fake `$`, feasibility to confirm): setSetting without a script / session id / with a failing set / unchanged value; a rejected click toasts (F-030); refreshSettings failures and unreadable JSON; warnings once (F-031)

## 5. Not counted as gaps

- Parity: no pane control for the project layer (by design, `/podium:config`).
- E2E backlog: none (no running application; e2e is out of scope for this repository, `scripts/merge-gate.conf`).

## 6. Run results (phase 3 ⇄ 4)

Phase 2 (16/11/2026, batch `fix/ti-batch`): pytest scripts/tests 1049 tests green under coverage, deno hooks 147 passed; coverage Python 92 % · TypeScript 99 % · shell 81.8 % (bash scripts/coverage.sh, exit 0, merge 7e4a9dd); QA two passes, the second with no serious gap.

## 7. Phase 2 — what closed each finding (16/11/2026)

| Id | Priority | Status | Closed by |
|---|---|---|---|
| [F-026](findings.md) | 🟡 | fixed | 2ab3eda, 4f872f9; one mode order a9722c4 (modes/README) |
| [F-027](findings.md) | 🟡 | fixed | 2ab3eda, 06fc5f4 (QA) |
| [F-028](findings.md) | 🟡 | fixed | 2ab3eda, 06fc5f4 (QA) |
| [F-029](findings.md) | 🟡 | fixed | b8cc475, 4db34ab |
| [F-030](findings.md) | 🟡 | fixed | c1f04ef |
| [F-031](findings.md) | 🟢 | fixed | 9592e98 |
| [F-032](findings.md) | 🟢 | fixed | a5da9de |
| [F-042](findings.md) | 🟡 | fixed | 2aab6c6 |
| [F-047](findings.md) | 🟢 | fixed | 6fc4b83 |
