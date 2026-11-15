# Test inventory — The gate (`scripts/gate-core.sh <dev|test|prod> (+ merge-gate.sh, CI sdlc.yml)`)

> Runs the shared step set (lint, types, build, unit, secrets, CVE, SAST, compat, md, coverage, e2e on request) and reports passed, waived or incomplete.
> Files: `scripts/gate-core.sh`, `gate-lib*.sh`, `merge-gate.sh/.conf`, `coverage.sh`, `coverage-shell.sh`, `codeql-scan.sh`, `audit-triage.py`, `require-private-remote.sh`, `pre-commit.sh`, `commit-msg.sh`, `real-name-check.sh`, `runner-setup.sh`, `sdlc_settings.py`, `twins.txt`, `.github/workflows/sdlc.yml`
>
> Audited: 14/11/2026 · branch `docs/test-inventory` · phase 1

## 1. Tests on this surface — by the numbers

py = `scripts/tests` (pytest) · deno = `hooks/*.test.ts` · engine = `hooks/register.test.tsx` (`claude plugin test`) · ci = `.github/workflows`. Web e2e, Android, iOS and Maestro do not exist in this repository: `—`.

| Layer | Files | Tests |
|---|---|---|
| py | 27 files: `test_gate_core_*`, `test_merge_gate_wrapper`, `test_coverage_*`, `test_codeql_scan`, `test_audit_triage`, `test_require_private_remote`, `test_pre_commit_steps`, `test_real_name_check`, `test_runner_setup`, `test_sdlc_settings`, `test_sdlc_workflow`, `test_podium_gate_steps`, `test_gate_node_install` | 354 (`pytest --collect-only -q`) |
| ci | `sdlc.yml` is checked only by `test_sdlc_workflow.py`; this repository has no caller workflow | — |

**Measured coverage:** `scripts/audit-triage.py` 97% · `scripts/sdlc_settings.py` 92% · `scripts/gate-core.sh` 76.4% · `scripts/gate-lib.sh` 66.7% · `scripts/coverage.sh` 99.0% · `scripts/codeql-scan.sh` 96.0% · `scripts/pre-commit.sh` 90.0% (command: `bash scripts/coverage.sh`, 14/11/2026).

## 2. Use cases and what is tested

`✅` tested · `◐` partly · `❌` not tested · `—` not implemented. Built from the code; the layer that tests each is named in the cell.

| # | Use case | Tested |
|---|---|---|
| 1 | Dispatch, usage, missing or stale libraries | ✅ |
| 2 | Step waiver: only `false` waives; locked secrets/SAST | ✅ |
| 3 | A skipped step → INCOMPLETE | ✅ |
| 4 | ACCEPTED_GAPS: coverage never acceptable | ◐ locked steps ARE acceptable (F-012) |
| 5 | Panel off → coverage only, exit 10 | ✅ |
| 6 | Panel source: live, file, CI | ✅ (old `adyusuf` plugin name falls back to the file, untested) |
| 7 | Coverage threshold | ◐ a lower COVERAGE_MIN is used (F-013) |
| 8 | coverage.sh Python/JS/TS NOT MEASURED paths | ✅ |
| 9 | Shell coverage | ◐ untraced scripts drop out (F-014) |
| 10 | Node steps, audit + triage, dotnet CVE, SAST thresholds | ✅ |
| 11 | Parallel Node track join | ◐ ticks only (F-017) |
| 12 | e2e and deploy checks on request | ✅ |
| 13 | pre-commit steps 0-4 | ◐ size-gate exit code (F-019) |
| 14 | CI plan job | ◐ non-boolean value (F-015) |
| 15 | sdlc-settings check in CI | ❌ (F-016) |

## 3. What is wrong — defects and unhandled cases

| Id | Priority | Class | Finding | Evidence |
|---|---|---|---|---|
| [F-012](findings.md) | 🔴 | Defect | The secret scan and SAST, locked "never switched off" (#19), can still be turned into ACCEPTED GAPs through `ACCEPTED_GAPS` + a reason: only `coverage` is in `NEVER_ACCEPTABLE`. The gate-core header even shows `ACCEPTED_GAPS="SAST\|…"` as an example. | `scripts/gate-lib.sh:20-30`, `scripts/gate-core.sh:88-95`; analyst B probe → `ACCEPTED GAP: gitleaks is not installed` |
| [F-013](findings.md) | 🟡 | Defect | `COVERAGE_MIN` has no floor: the header says the environment may only raise the 80 % threshold (#29), but any lower value is used as is. | `scripts/gate-core.sh:70,128`, `scripts/coverage.sh:29`, `scripts/coverage-shell.sh:58`; analyst B probe `COVERAGE_MIN=10` → passed |
| [F-014](findings.md) | 🟡 | Defect | The shell coverage denominator is only the files kcov traced: a new `scripts/*.sh` that no test runs vanishes instead of being NOT MEASURED (JS and TS do report it). The exclusion list lives in three places, not one (#29). | `scripts/coverage-shell.sh:152-170`, `.coveragerc`, `scripts/coverage.sh:121` |
| [F-015](findings.md) | 🟡 | Unhandled case | The CI `plan` job runs the gate only when the value is exactly `true`; any other value skips it and the skipped job reads green, the opposite of the local gate (only an explicit `false` waives). | `.github/workflows/sdlc.yml:66,79` |
| [F-016](findings.md) | 🟡 | Unhandled case | Nothing in CI checks the committed `.claude/sdlc-settings.json`: a PR that edits it can turn off CI, coverage and every unlocked gate step. Whether a committed file is the panel's word is a user decision. | `scripts/sdlc_settings.py` (`check` has no caller in `.github/`), `scripts/gate-lib.sh:126-130` |
| [F-018](findings.md) | 🟡 | Unhandled case | CodeQL looks for `*.js` only; this repository has none, so the TypeScript mod (`hooks/*.ts`, `*.tsx`) is never scanned and the step prints `n/a`, not NOT RUN. | `scripts/codeql-scan.sh:117-119`; `find . -name "*.js"` → nothing |
| [F-019](findings.md) | 🟡 | Defect | pre-commit step 1 ignores the size gate's exit code (`\|\| true`) and blocks only on the words CEILING EXCEEDED or NO BUDGET: a missing budgeted CLAUDE.md, a missing budget file, a crash or the bad row of F-022 all let the commit through. | `scripts/pre-commit.sh:79-87` |
| [F-020](findings.md) | 🟢 | Unhandled case | Without `timeout`/`gtimeout` (default macOS) the dotnet CVE listing runs unbounded, although the comment says no answer in time is a failure; an `ACCEPTED_GAPS` regex with an empty branch would match every label but coverage. | `scripts/gate-core.sh:228-229`, `scripts/gate-lib.sh:23` |
| [F-021](findings.md) | 🟢 | Dead code | A docstring after a statement in `audit-triage.py` is dead text; `test_gate_core_fixes.py` (399 lines) and `test_gate_core_prod.py` (404) are over the 300-line rule (#9). | `scripts/audit-triage.py:85`; `wc -l` |
| [F-042](findings.md) | 🟡 | Defect | The coverage step is red for the whole repository: `coverage.sh` type-checks the TypeScript tests, the 2 known `.not` failures in `hooks/status.test.ts` fail that check, so TypeScript coverage is "not a measurement" and `coverage.sh` exits 1 although Python (90 %) and shell (81 %) pass. Every gate with coverage on is therefore red. | `bash scripts/coverage.sh` → "TS2339 Property 'not' does not exist", "✗ the tests are red", exit 1 (14/11/2026); `scripts/ts-shim/claude-code-testing.ts:6-10` |

## 4. What is missing — test gaps

| Id | Priority | Gap | Evidence | Phase 2 |
|---|---|---|---|---|
| [F-017](findings.md) | 🟡 | The parallel Node track (`GATE_PARALLEL_NODE=1`) promises "a track that did not report counts as FAILED", but no test kills a track or checks the join. | `scripts/gate-lib-node.sh:114-119,158-168`; only `test_gate_core_steps.py:203` | pending |

**Proposed phase-2 tests** (written only after approval; a defect's regression test is written with its approved fix):

- py: a missing gitleaks or SAST cannot be accepted (F-012)
- py: a lower COVERAGE_MIN is clamped to 80 (F-013)
- py: an untraced script is NOT MEASURED (F-014)
- py: a non-boolean ci value still runs the checks (F-015)
- py: CI runs coverage even when the file waives it (F-016, only if decided)
- py: a dying node track closes the gate; non-zero exit (F-017, 2 tests)
- py: TypeScript counts for the JavaScript pass (F-018)
- py: a crashed or missing-file size gate stops the commit (F-019, 2 tests)
- py: no timeout tool is reported (F-020)

## 5. Not counted as gaps

- Parity: none.
- E2E backlog: none (no running application; e2e is out of scope for this repository, `scripts/merge-gate.conf`).

## 6. Run results (phase 3 ⇄ 4)

Phase 2 (16/11/2026, batch `fix/ti-batch`): pytest scripts/tests 1049 tests green under coverage, deno hooks 147 passed; coverage Python 92 % · TypeScript 99 % · shell 81.8 % (bash scripts/coverage.sh, exit 0, merge 7e4a9dd); QA two passes, the second with no serious gap.

## 7. Phase 2 — what closed each finding (16/11/2026)

| Id | Priority | Status | Closed by |
|---|---|---|---|
| [F-012](findings.md) | 🔴 | fixed | 86da8b8, c1d5b9b |
| [F-013](findings.md) | 🟡 | fixed | 71eb590 |
| [F-014](findings.md) | 🟡 | fixed | 71eb590, 23d2b7f |
| [F-015](findings.md) | 🟡 | fixed | 7c06316 |
| [F-016](findings.md) | 🟡 | closed by decision | 7c06316 (CI prints what the committed settings waive); decision a9722c4 (standards/13 §8a) |
| [F-017](findings.md) | 🟡 | fixed | 93b88ea |
| [F-018](findings.md) | 🟡 | fixed | d0d674f |
| [F-019](findings.md) | 🟡 | fixed | 334bcf2 |
| [F-020](findings.md) | 🟢 | fixed | 86da8b8 |
| [F-021](findings.md) | 🟢 | fixed | afbba4a |
| [F-042](findings.md) | 🟡 | fixed | 2aab6c6 |
