# Test inventory — Agents box and rule injection (`pane Agents box · rules-context.py`)

> Shows each role with its model and lets the user switch roles and models; injects CLAUDE.md into sessions and subagents.
> Files: `hooks/boxes.ts` (`agentsBody`), `scripts/podium_schema.py` (`agents`, role sets), `agents/*.md`, `modes/*.md`, `scripts/rules-context.py`
>
> Audited: 14/11/2026 · branch `docs/test-inventory` · phase 1

## 1. Tests on this surface — by the numbers

py = `scripts/tests` (pytest) · deno = `hooks/*.test.ts` · engine = `hooks/register.test.tsx` (`claude plugin test`) · ci = `.github/workflows`. Web e2e, Android, iOS and Maestro do not exist in this repository: `—`.

| Layer | Files | Tests |
|---|---|---|
| py | `test_rules_context.py`, `test_rules_context_cli.py`, agents block of `test_podium_config.py` | 45 + 10 |
| deno | agents tests in `boxes.test.ts` | ≈12 (`grep`) |

**Measured coverage:** `scripts/rules-context.py` 100% · `scripts/podium_schema.py` 100% (command: `bash scripts/coverage.sh`, 14/11/2026).

## 2. Use cases and what is tested

`✅` tested · `◐` partly · `❌` not tested · `—` not implemented. Built from the code; the layer that tests each is named in the cell.

| # | Use case | Tested |
|---|---|---|
| 1 | agents(): mode × enabled × model | ✅ py |
| 2 | Role press and model press | ✅ deno (mode A model press: F-034) |
| 3 | Box when data is missing / role off / no description | ✅ deno |
| 4 | Mode documents match MODE_ROLES | ◐ B and C only (F-033) |
| 5 | rules-context: 4 parts under 10,000 characters, unreadable file | ✅ py |
| 6 | Multi-line description | ❌ (F-034) |

## 3. What is wrong — defects and unhandled cases

| Id | Priority | Class | Finding | Evidence |
|---|---|---|---|---|
| [F-026](findings.md) | 🟡 | Unhandled case | No script reads `.claude/mode` or the session scratchpad mode, which the rules and the working-mode skill rank above the config `mode`; the session-start "mode X" line, `agents` and the Agents box use the config key alone and can disagree with the mode in force. | `scripts/podium_config.py:92`, `scripts/podium_schema.py:153`; `grep -rln ".claude/mode" scripts hooks` → only a comment |
| [F-034](findings.md) | 🟢 | Unhandled case | A model press in mode A writes a setting that has no effect; `front_matter` reads only a single-line `description:`; an unreadable CLAUDE.md leaves the session without its rules, with only a hook stderr line. | `hooks/boxes.ts:247-256`, `scripts/podium_schema.py:125-134`, `scripts/rules-context.py:125-130` |

## 4. What is missing — test gaps

| Id | Priority | Gap | Evidence | Phase 2 |
|---|---|---|---|---|
| [F-033](findings.md) | 🟡 | Only modes B and C are pinned to their documents; `MODE_ROLES` for D and E has no oracle outside the code. | `scripts/tests/test_podium_config.py:590-603` | pending |

**Proposed phase-2 tests** (written only after approval; a defect's regression test is written with its approved fix):

- py: mode D names the fourteen roles; mode E says it is D (F-033, 2 tests)
- py: a multi-line description (F-034)
- deno: a model press in mode A (F-034)

## 5. Not counted as gaps

- Parity: none.
- E2E backlog: none (no running application; e2e is out of scope for this repository, `scripts/merge-gate.conf`).

## 6. Run results (phase 3 ⇄ 4)

Phase 2 (16/11/2026, batch `fix/ti-batch`): pytest scripts/tests 1049 tests green under coverage, deno hooks 147 passed; coverage Python 92 % · TypeScript 99 % · shell 81.8 % (bash scripts/coverage.sh, exit 0, merge 7e4a9dd); QA two passes, the second with no serious gap.

## 7. Phase 2 — what closed each finding (16/11/2026)

| Id | Priority | Status | Closed by |
|---|---|---|---|
| [F-026](findings.md) | 🟡 | fixed | 2ab3eda, 4f872f9; one mode order a9722c4 (modes/README) |
| [F-033](findings.md) | 🟡 | fixed | 41cc779 |
| [F-034](findings.md) | 🟢 | fixed | c063ca8, 41cc779, da4658a, 4db34ab |
