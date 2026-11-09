// What the hover cards of the podium pane say (user decision 01/11/2026): one short text per box, per Settings tab and
// per Settings row, shown while the pointer rests on its title or label. An Agents role shows its own agent file's
// `description:` instead, so a role is described in one place. Keyed by the label the pane draws.

/** The boxes, by section id. */
export const SECTION_HELP: Record<string, string> = {
  status: 'What this session is doing now, what comes next, and one row per piece with its measured figure.',
  settings: 'What Claude follows instead of asking, for code in a project. Outside a repository only the rows for work without code show.',
  agents: 'Every role, ticked when it runs, with the model it runs on. Tick or untick one for this session.',
  promotion: 'Where dev, test and prod stand on origin, and any gate waived on the commits waiting to come in.',
}

/** The two tabs of the Settings box. */
export const COLUMN_HELP: Record<string, string> = {
  Session: 'This tab: what this session runs on. A press changes this session only; a new session starts from System.',
  System: 'This tab: your saved defaults (~/.claude/podium.json), under any project file. New sessions start from them.',
}

/** The Settings rows, by the label the pane shows. */
export const ROW_HELP: Record<string, string> = {
  'Mode': 'How many agents work: A none, B three helpers, C the full team with qa review, D wide team, E fan-out.',
  'Model*': 'The model the roles marked * in Agents run on instead of Opus. opus keeps them on Opus.',
  'Replies': 'How much Claude writes: short, normal or long. Red tests and skipped steps are said at every length.',
  'Budget': 'US dollars for this session, shown in Status against the measured spend (list price). Never a stop: work goes on past it.',
  'Plan': 'Every task is split into steps in Status first. force: no code edit or commit until the steps exist. remind: only a reminder.',
  'Pod': 'Connect to a pod. Stored only; nothing acts on it yet.',
  'Pod message': 'The pod message format. Stored only; nothing acts on it yet.',
  'Tests': 'Whether Claude writes unit tests and e2e specs for its changes.',
  'Merge': 'Which branches Claude merges finished work into, without asking.',
  'Push': 'Which branches Claude pushes after merging, without asking.',
  'Gates': 'Run the shared gate (lint, build, tests, scans) before pushing to that branch. Off is recorded as Gate-Waived. The arrow opens its steps.',
  'Coverage': 'Measure line coverage (80% per codebase) before pushing to that branch.',
  'CI': 'Wait for CI to pass after pushing to that branch.',
  'Runner': 'Where CI runs: cloud (GitHub runners) or local (this machine).',
  'Deploy': 'Which environments a pushed update is deployed to.',
  'E2E': 'Run the e2e suite before deploying to that environment.',
}

/** Every gate step row's card, after the step's own heading from the gate (gate-lib.sh), so no step is named here. */
export const STEP_HELP = 'a step of the shared gate. Unticked, it does not run on that branch; the gate reports it as waived and the merge names it in Gate-Waived, never as passed.'

/** A locked step's card (the secret scan and SAST), after its heading: why its tick cannot be changed. */
export const LOCKED_STEP_HELP = 'always on. Rule #19: security scans are never switched off, so this tick cannot be removed and the gate runs it even if a settings file says no.'
