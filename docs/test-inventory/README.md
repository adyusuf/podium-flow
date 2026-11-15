# Test inventory — index

> Updated: 16/11/2026 · surfaces in risk order (security and data loss → gate integrity → settings that act without asking → views). This repository is the `podium` plugin, so a "screen" is a surface: a hook, a script family or a pane box.

| # | Surface | Entry | Phase | 🔴 | 🟡 | 🟢 | Open · in progress · closed | Top finding | Report |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Installer | `scripts/plugin-setup.py` | 1 · 2 | 0 | 6 | 1 | 0 · 0 · 7 | F-008: installer rewrites settings.json in place, not atomically | [installer.md](installer.md) |
| 2 | Guards | `PreToolUse hooks: guard-destructive.sh, podium_status.py hook guard` | 1 · 2 | 3 | 4 | 1 | 0 · 0 · 8 | F-001: guard lets forced and destructive pushes through | [guards.md](guards.md) |
| 3 | The gate | `scripts/gate-core.sh <dev\|test\|prod> (+ merge-gate.sh, CI sdlc.yml)` | 1 · 2 | 1 | 8 | 2 | 0 · 0 · 11 | F-012: secret scan and SAST can be accepted away | [gate.md](gate.md) |
| 4 | Settings box and settings engine | `pane Settings box · scripts/podium_config.py` | 1 · 2 | 0 | 6 | 3 | 0 · 0 · 9 | F-028: one bad value drops a whole settings layer silently | [settings.md](settings.md) |
| 5 | Status box and status engine | `pane Status box · scripts/podium_status.py` | 1 · 2 | 0 | 5 | 5 | 0 · 0 · 10 | F-006: a non-numeric percent locks every edit | [status.md](status.md) |
| 6 | Agents box and rule injection | `pane Agents box · rules-context.py` | 1 · 2 | 0 | 2 | 1 | 0 · 0 · 3 | F-026: no script reads the mode files | [agents.md](agents.md) |
| 7 | Promotion box | `pane Promotion box` | 1 · 2 | 0 | 2 | 1 | 0 · 0 · 3 | F-035: Promotion box hides git errors | [promotion.md](promotion.md) |
| 8 | Doc gates | `md-size-gate.sh, md-hook.sh, md-rule-gate.py, doc-check.py, evidence-check.py, twin-drift.sh` | 1 · 2 | 1 | 4 | 1 | 0 · 0 · 6 | F-022: size gate passes a malformed budget row | [doc-gates.md](doc-gates.md) |

**Totals** (a finding on two surfaces counts on each): 🔴 5 · 🟡 37 · 🟢 15. **Distinct findings: 48** (🔴 5 · 🟡 28 · 🟢 15), 0 open (phase 2, 16/11/2026: 42 from phase 1 + 6 found while fixing, F-043..F-048).

The counts are computed from the register's screen column by a script from the register (doc-sync §4), never typed.

## Findings that span several surfaces

- **The mod's glue is untested** ([F-029](findings.md)): `register.tsx` holds the click, refresh and read paths of Settings, Status and Promotion, and the only engine test mounts the pane. Several 🟡 defects ([F-030](findings.md), [F-035](findings.md), [F-037](findings.md)) sit in that untested code.
- **Fail-open where the rules ask fail-closed** (#6, #19, #25): guard bypasses ([F-001](findings.md), [F-002](findings.md)), accepted-away scans ([F-012](findings.md)), a size gate passing a bad row ([F-022](findings.md)), pre-commit ignoring an exit code ([F-019](findings.md)), a steps guard opening on a bad payload ([F-005](findings.md)), a Promotion box hiding git errors ([F-035](findings.md)), a settings layer dropped silently ([F-028](findings.md)).
- **Rules written but not wired**: evidence-check and doc-check run in no gate or CI ([F-023](findings.md), [F-024](findings.md)); the mode files are read by no script ([F-026](findings.md)).

All three are closed (phase 2, 16/11/2026): the glue moved to `hooks/glue.ts`/`hooks/port.ts` with tests through a fake `$`, every fail-open path fails closed with a regression test, and the unwired rules are wired (F-026) or decided as commit-time / on demand (F-023, F-024).

## Not confirmed (kept out of the register)

- real-name-check with non-ASCII file names (octal-quoted by git) and `#` lines in a `-m` message: not probed.
- A Windows `CLAUDE_CODE_PLUGIN_DIRS` written with `/` separators is not repointed: not run on Windows.
- Whether an exported lower `COVERAGE_MIN` reaches `coverage.sh` through `bash -c` (the floor gap itself, F-013, is confirmed in the code).

## Observations, not findings

- `CLAUDE.md` is 23,550 bytes against a 23 KB ceiling (23,552): two bytes of headroom (`wc -c CLAUDE.md`).
- Already known and not re-reported: 2 deno tests fail (shim lacks `.not`); doc-check "README states 39 scripts, the repository has 41"; `hooks/boxes.test.ts` and `scripts/tests/test_podium_config.py` over 300 lines; refreshSettings not serialised. Since closed in phase 2: the `.not` shim (F-042), the README count (42 scripts), refreshSettings serialised (F-031).

## E2E backlog

None: this repository has no running application (`scripts/merge-gate.conf` accepts the e2e checks as inapplicable).

## Parity backlog

None.
