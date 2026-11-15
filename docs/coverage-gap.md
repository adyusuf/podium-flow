# Coverage — this repository's own scripts (global rule #29)

Measured with `bash scripts/coverage.sh` (line coverage, `coverage` 7.10 in a venv
outside the repository, subprocesses included). The denominator is every hand-written
script; only `scripts/tests/` is omitted (`.coveragerc`). Nothing else is excluded.

> This file used to be a **gap** report: Python at 52% with four scripts at 0%, and
> the shell codebase NOT MEASURED. Both are closed. It is kept as the record of what
> closing them took, and of what is still thin.

## Where it stands

⚠️ **These figures are a snapshot, not a gate.** The gate is `scripts/coverage.sh`,
which measures before every push the coverage setting turns on; this file is a written record and it goes stale the
moment a test lands. It has gone stale twice already. Refresh it with the command at
the top and correct the numbers in the same commit as the tests that moved them.


| Codebase | Coverage | State |
|---|---|---|
| Python scripts | **92%** (2,409 of 2,627 statements; measured 16/11/2026, after the test-inventory batch) | above the 80% threshold |
| Shell scripts | **81.8%** (863 of 1,055 lines, 538 traced runs; measured 16/11/2026, `scripts/*.sh`; every script traced, none NOT MEASURED) | above the 80% threshold |
| TypeScript mod logic (`hooks/*.ts`) | **99%** (908 of 910 lines; measured 16/11/2026; `hooks/register.tsx` is the one listed exclusion, engine glue - `standards/10` §7.2a) | above the 80% threshold |

All three from `bash scripts/coverage.sh` (exit 0) on the batch merge 7e4a9dd. Before the batch (14/11/2026): Python 90%,
shell 81.0%, TypeScript not measured (the suite failed type-check on two `.not` assertions,
[`test-inventory/findings.md`](test-inventory/findings.md) F-042, fixed by 2aab6c6).

No figure is an average of another. #29 forbids averaging codebases, and the
gate reads them separately — any one below 80% closes it.

## What is still thin

Above the threshold is not the same as well tested. The weakest files, worth knowing
before trusting them:

| File | Coverage | Why it matters |
|---|---|---|
| `scripts/step-stats.py` + its three `step_stats_*.py` parts | **63%** over the four files (125 of 334 statements missed; `step-stats.py` itself 37%, measured 13/10/2026 after the split) | `compare_cuts`, `report` and `main` — the functions that WRITE the document — are still untested. The sanitiser and the attribution below them are covered, and the sanitiser is the half that must not leak |
| `scripts/guard-destructive.sh` | **63.6%** | the hook that refuses `rm -rf`, force push and `DROP`. ⚠️ **The uncovered lines ARE tested** — `GuardFailsClosed` in `scripts/tests/test_guard_destructive.py` covers all of them, and mutation confirms it: `exit 0` in either branch turns those tests red. They do not COUNT because the cases are "the inspector is not beside the script" and "the inspector answers wrongly", which need a directory without the real inspector — so the tests run a copy, and a tracer credits the file it ran. The alternative is an env var that redirects the inspector: a way to redirect the guard, placed inside the guard. The unmeasured line is the cheaper problem |
| `scripts/real-name-check.sh` | **75%** | the commit-message guard |
| `scripts/gate-lib-panel.sh`, `gate-lib-node.sh`, `gate-lib.sh`, `gate-core.sh` | **17.4%, 46.8%, 68.8%, 76.5%** (16/11/2026) | the gate's own libraries, the thinnest shell files; why their lines go unreported has not been investigated. The shell total is above 80% because the smaller scripts are near 100% |
| `scripts/coverage-shell.sh` | **89.4%** (16/11/2026) | the tracer wrapper: it measures, and is itself measured |

`scripts/merge-gate.sh` used to head this table at 0%. It is at 100% now, and getting
there took two attempts: the first set of tests passed every assertion while coverage
stayed at 0.0%, because they ran a COPY of the wrapper. A test that exercises a copy
proves the logic and measures nothing.

## How the shell codebase became measurable

It was reported as NOT MEASURED for two separate reasons, and both had to go:

- **`kcov` could not trace the macOS system bash** (`Can't find or open /bin/bash` —
  SIP). It traces the Homebrew bash instead, and `coverage.sh` prints which
  interpreter the number belongs to on every run.
- **Most shell tests ran a temporary *copy*** of the script in a throwaway
  repository, and no tracer attributes a copy back to the original. The tests were
  changed to run the scripts **in place**; that change is what made the number exist
  at all, and the reasoning is in `scripts/coverage-shell.sh`.

## The rule that keeps it honest

Each added test must catch a fault under mutation (`standards/10-test-strategy.md`
§7). A test that only executes lines is fake coverage, and adding one is the same as
loosening the threshold — which #29 forbids outright. The exclusion list stays in one
place with a reason per entry, and only generated code may be on it.
