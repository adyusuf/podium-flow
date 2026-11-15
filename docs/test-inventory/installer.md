# Test inventory — Installer (`scripts/plugin-setup.py`)

> Installs, updates or moves the `podium` plugin on a user's machine through the `claude plugin` CLI.
> Files: `scripts/plugin-setup.py` (419 lines, the written rule-#9 exception); docs `README.md` install, `SETUP.md` §6, `scripts/README.md`
>
> Audited: 14/11/2026 · branch `docs/test-inventory` · phase 1

## 1. Tests on this surface — by the numbers

py = `scripts/tests` (pytest) · deno = `hooks/*.test.ts` · engine = `hooks/register.test.tsx` (`claude plugin test`) · ci = `.github/workflows`. Web e2e, Android, iOS and Maestro do not exist in this repository: `—`.

| Layer | Files | Tests |
|---|---|---|
| py | `test_plugin_setup.py`, `_claude`, `_legacy`, `_refusals`, `_replace` (+ `plugin_setup_helpers.py`) | 65 (`pytest --collect-only -q`) |

**Measured coverage:** `scripts/plugin-setup.py` 99% (command: `bash scripts/coverage.sh`, 14/11/2026).

## 2. Use cases and what is tested

`✅` tested · `◐` partly · `❌` not tested · `—` not implemented. Built from the code; the layer that tests each is named in the cell.

| # | Use case | Tested |
|---|---|---|
| 1 | Ref and argument validation; locating `claude` and `git` | ✅ |
| 2 | Marketplace list read, non-GitHub source refused, remote sha lookup | ✅ |
| 3 | Fresh install, current, `--check`, replace (ask / `--yes` / no tty) | ✅ |
| 4 | Keep settings across a replace (backup, re-disable) | ✅ |
| 5 | Legacy `adyusuf` → `podium` move | ◐ no `--yes` without tty, project scope, old link without old install |
| 6 | Repoint `CLAUDE_CODE_PLUGIN_DIRS` | ◐ no Windows separators, malformed settings, atomicity |
| 7 | Log file in `finally` | ◐ content and unwritable home untested |
| 8 | Child timeout → 127 | ❌ |
| 9 | Rerun after a partial legacy move | ❌ (and mishandled: F-007) |

## 3. What is wrong — defects and unhandled cases

| Id | Priority | Class | Finding | Evidence |
|---|---|---|---|---|
| [F-007](findings.md) | 🟡 | Unhandled case | After a failed removal of the old `adyusuf` plugin (or a hand-made new link) a rerun never retries the removal: the legacy branch is entered only while the new marketplace link is missing. | `scripts/plugin-setup.py:271-272` (`if (old or old_market) and market is None`) |
| [F-008](findings.md) | 🟡 | Defect | `repoint_plugin_dirs` rewrites `~/.claude/settings.json` in place (`open("w")` + `json.dump`): not atomic, no lock, whole file re-serialised. A backup copy is taken first. | `scripts/plugin-setup.py:204-210` |
| [F-009](findings.md) | 🟡 | Unhandled case | An unreadable or invalid `settings.json` is read as `{}`, so a disabled plugin is not re-disabled after a replace, with no warning. | `scripts/plugin-setup.py:106-114` |
| [F-011](findings.md) | 🟢 | Unhandled case | `connect()` failing in the "current but link missing" path still returns 0; the log write in `finally` raises on an unwritable home and masks the real exit code; a child timeout (600 s → 127) is untested. | `scripts/plugin-setup.py:279-281,411-415` |

## 4. What is missing — test gaps

| Id | Priority | Gap | Evidence | Phase 2 |
|---|---|---|---|---|
| [F-010](findings.md) | 🟡 | The legacy move promises the settings carry on unchanged, but no test checks `podium.json` byte for byte after a move (the replace path has that test). | `scripts/plugin-setup.py:215-234`; `README.md:10` | pending |

**Proposed phase-2 tests** (written only after approval; a defect's regression test is written with its approved fix):

- py: rerun after a failed legacy removal retries it (F-007)
- py: legacy `--yes` without a tty; legacy in project scope; old link without old install
- py: corrupt settings.json is reported (F-009)
- py: repoint keeps other keys and non-ASCII, atomic (F-008); Windows separators
- py: legacy move leaves podium.json byte-identical (F-010)
- py: child timeout → 127; unwritable log folder keeps the exit code (F-011)

## 5. Not counted as gaps

- Parity: none (one layer).
- E2E backlog: none (no running application; e2e is out of scope for this repository, `scripts/merge-gate.conf`).

## 6. Run results (phase 3 ⇄ 4)

Phase 2 (16/11/2026, batch `fix/ti-batch`): pytest scripts/tests 1049 tests green under coverage, deno hooks 147 passed; coverage Python 92 % · TypeScript 99 % · shell 81.8 % (bash scripts/coverage.sh, exit 0, merge 7e4a9dd); QA two passes, the second with no serious gap.

## 7. Phase 2 — what closed each finding (16/11/2026)

| Id | Priority | Status | Closed by |
|---|---|---|---|
| [F-007](findings.md) | 🟡 | fixed | f077526 |
| [F-008](findings.md) | 🟡 | fixed | a98d05b, 50045aa |
| [F-009](findings.md) | 🟡 | fixed | d27cc9e |
| [F-010](findings.md) | 🟡 | fixed | 40c72b6 |
| [F-011](findings.md) | 🟢 | fixed | 468ba7d |
| [F-043](findings.md) | 🟡 | fixed | dfe69b6 |
| [F-044](findings.md) | 🟡 | fixed | 7c8b721 |
