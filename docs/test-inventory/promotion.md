# Test inventory — Promotion box (`pane Promotion box`)

> Reads the branches and the Gate-Waived lines waiting to come into each stage.
> Files: `hooks/register.tsx` (`refreshPromotion`), `hooks/choose.ts` (`plannedStages`, `waivedRange`, `waivedLines`), `hooks/boxes.ts` (`promotionBody`)
>
> Audited: 14/11/2026 · branch `docs/test-inventory` · phase 1

## 1. Tests on this surface — by the numbers

py = `scripts/tests` (pytest) · deno = `hooks/*.test.ts` · engine = `hooks/register.test.tsx` (`claude plugin test`) · ci = `.github/workflows`. Web e2e, Android, iOS and Maestro do not exist in this repository: `—`.

| Layer | Files | Tests |
|---|---|---|
| deno | `choose.test.ts` (3 on this box), `boxes.test.ts` (1) | 4 |
| engine | `register.test.tsx` | header mounts only |

**Measured coverage:** `hooks/choose.ts` not measured (the TS suite failed type-check: F-042) · `hooks/boxes.ts` not measured (the TS suite failed type-check: F-042) (command: `bash scripts/coverage.sh`, 14/11/2026).

## 2. Use cases and what is tested

`✅` tested · `◐` partly · `❌` not tested · `—` not implemented. Built from the code; the layer that tests each is named in the cell.

| # | Use case | Tested |
|---|---|---|
| 1 | Outside a repository → two-section pane | ✅ deno |
| 2 | Stages from origin refs | ✅ deno |
| 3 | for-each-ref / rev-parse / rev-list / log failures | ◐ render only; ❌ the exit codes (F-035) |
| 4 | A body line starting with `@@` | ◐ (F-036) |
| 5 | Concurrent refreshes | ❌ (F-036) |

## 3. What is wrong — defects and unhandled cases

| Id | Priority | Class | Finding | Evidence |
|---|---|---|---|---|
| [F-035](findings.md) | 🟡 | Defect | The Promotion box fails open on git errors: a failed `git log` shows "no waived gate on the way in", a failed `rev-list` shows "pushed", a failed `rev-parse` a blank origin; their exit codes are not checked. The box exists to list waived gates before a prod merge (#34). | `hooks/register.tsx:107-116` |
| [F-036](findings.md) | 🟢 | Unhandled case | Text drift on what the waived range is ("came in" vs "waiting to come in"); a commit body line starting with `@@` resets the parsed sha; refreshPromotion is not serialised. | `hooks/choose.ts:34-42,129-131`, `hooks/help.ts` STAGE_TAIL |

## 4. What is missing — test gaps

| Id | Priority | Gap | Evidence | Phase 2 |
|---|---|---|---|---|
| [F-029](findings.md) | 🟡 | The mod's data paths in `register.tsx` (setSetting, the click queue, refreshSettings, refreshPromotion, readStatus, the poll, waitAfterInterrupt) have no test: the engine test only mounts the pane, and its comment says they are exercised by hand. | `hooks/register.test.tsx:3-6`, `hooks/register.tsx:54-143,156-253` | pending |

**Proposed phase-2 tests** (written only after approval; a defect's regression test is written with its approved fix):

- deno (fake `$.process.run`): each git failure shows "could not read"; no local branch; `@@` in a body (F-035, F-036)

## 5. Not counted as gaps

- Parity: none.
- E2E backlog: none (no running application; e2e is out of scope for this repository, `scripts/merge-gate.conf`).

## 6. Run results (phase 3 ⇄ 4)

Not run yet.
