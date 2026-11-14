# Test inventory — Doc gates (`md-size-gate.sh, md-hook.sh, md-rule-gate.py, doc-check.py, evidence-check.py, twin-drift.sh`)

> Size ratchet for CLAUDE.md, rule-loss check, link/count checks, evidence-block check, twin drift.
> Files: `scripts/md-size-gate.sh`, `md-budget.tsv`, `md-hook.sh`, `md_hook_path.py`, `md-rule-gate.py`, `md-gate-triage.json`, `md-split.py`, `doc-check.py`, `evidence-check.py`, `evidence-block.schema.json`, `twin-drift.sh`
>
> Audited: 14/11/2026 · branch `docs/test-inventory` · phase 1

## 1. Tests on this surface — by the numbers

py = `scripts/tests` (pytest) · deno = `hooks/*.test.ts` · engine = `hooks/register.test.tsx` (`claude plugin test`) · ci = `.github/workflows`. Web e2e, Android, iOS and Maestro do not exist in this repository: `—`.

| Layer | Files | Tests |
|---|---|---|
| py | `test_md_size_gate*.py`, `test_md_hook_*.py`, `test_md_rule_gate.py`, `test_md_split.py`, `test_doc_check.py`, `test_evidence_check.py`, `test_twin_drift.py` | 198 (`grep -c "def test_"`) |

**Measured coverage:** `scripts/md-rule-gate.py` 93% · `scripts/md-split.py` 99% · `scripts/doc-check.py` 89% · `scripts/evidence-check.py` 85% · `scripts/md-size-gate.sh` 96.1% · `scripts/md-hook.sh` 100.0% · `scripts/twin-drift.sh` 100.0% (command: `bash scripts/coverage.sh`, 14/11/2026).

## 2. Use cases and what is tested

`✅` tested · `◐` partly · `❌` not tested · `—` not implemented. Built from the code; the layer that tests each is named in the cell.

| # | Use case | Tested |
|---|---|---|
| 1 | Size audit, --init, --update, --hook | ✅ |
| 2 | A malformed budget row | ❌ and passes (F-022) |
| 3 | md-hook edit/Stop and twin drift | ✅ |
| 4 | md-rule-gate lost/truncated/inverted, triage | ✅ (missing file argument ❌) |
| 5 | doc-check checks 1-6 | ✅ (CLI path ◐) |
| 6 | evidence-check | ✅ (thin blocks pass: F-025) |
| 7 | twin-drift | ✅ (stale origin/dev: F-025) |
| 8 | Wiring into gate/CI | ◐ doc-check and evidence-check not wired (F-023, F-024) |

## 3. What is wrong — defects and unhandled cases

| Id | Priority | Class | Finding | Evidence |
|---|---|---|---|---|
| [F-019](findings.md) | 🟡 | Defect | pre-commit step 1 ignores the size gate's exit code (`\|\| true`) and blocks only on the words CEILING EXCEEDED or NO BUDGET: a missing budgeted CLAUDE.md, a missing budget file, a crash or the bad row of F-022 all let the commit through. | `scripts/pre-commit.sh:79-87` |
| [F-022](findings.md) | 🔴 | Defect | A non-numeric ceiling or target in `md-budget.tsv` makes the size gate report the row "under the ceiling" and exit 0: `[ "$now" -gt "abc" ]` errors and the `if` takes the false branch (no `set -e`). | `scripts/md-size-gate.sh:135-142`; probe 40 KB CLAUDE.md + row `abc` → "✓ Every CLAUDE.md is within its budget", exit 0 |
| [F-023](findings.md) | 🟡 | Unhandled case | `evidence-check.py` (rule #28: a role output without its evidence block is unaudited) is called by no hook, gate or workflow; only documents name it. | `grep -rn evidence-check` → docs, twins.txt and itself |
| [F-024](findings.md) | 🟡 | Unhandled case | `doc-check.py` runs only in pre-commit (and not for the live config); gate-core and CI do not run it, so a red doc-check never stops a promotion. | `scripts/pre-commit.sh:101-107`; no hit in `scripts/gate-*.sh`, `.github/` |
| [F-025](findings.md) | 🟢 | Unhandled case | `md-gate-triage.json` is not in `twins.txt` (a project copy can drift unseen); twin-drift compares against the local `origin/dev` without fetching; evidence-check accepts very thin blocks; the size gate matches listed paths as an unescaped regex. | `scripts/twins.txt`, `scripts/twin-drift.sh:68`, `scripts/evidence-block.schema.json:9-12`, `scripts/md-size-gate.sh:167` |

## 4. What is missing — test gaps

| Id | Priority | Gap | Evidence | Phase 2 |
|---|---|---|---|---|
| — | | the gaps of this surface are the tests attached to its defects (below) | | |

**Proposed phase-2 tests** (written only after approval; a defect's regression test is written with its approved fix):

- py: a non-numeric ceiling and a short row close the gate (F-022, 2 tests)
- py: the gate lists doc-check, if decided (F-024)
- py: twin-drift reports a copy without its triage file (F-025)
- py: md-rule-gate with a missing file exits non-zero
- py: doc-check CLI exits 1 on a finding

## 5. Not counted as gaps

- Parity: none.
- E2E backlog: none (no running application; e2e is out of scope for this repository, `scripts/merge-gate.conf`).

## 6. Run results (phase 3 ⇄ 4)

Not run yet.
