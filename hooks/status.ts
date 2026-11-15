// What the Status box of the podium pane shows: this session's status table (user decision 01/11/2026), the same table
// `standards/00-working-method.md` §10 asks for in a reply during a long run. Engine-free like boxes.ts, so a test hands in
// a recording factory. The file is written by scripts/podium_status.py; register.tsx reads it and hands its text here.
import { type FoldId, isFolded, type Ui } from './boxes'
import { explained, helpCard, INDENT } from './controls'
import { STATUS_HELP } from './help'

/** A step (user decision 02/11/2026): `percent` done ('' when not given), `blocker`, `agent` ('' = this session) and, on a
 *  subagent's row, `label` - `<description> (<model>)`, the title its accordion shows (layer 2, 16/11/2026). */
type StatusRow = { item: string; state: string; figure: string; waiting: string; percent: string; blocker: string; agent: string; note: string; label: string }
/** `budget` (user decision 06/11/2026): this session's measured spend against the panel's budget, one line; shown, never a stop. */
export type StatusData = { now: string; next: string; rows: StatusRow[]; updated: string; budget: string }

/** The same caps as scripts/podium_status.py: the file is read as untrusted text, so a foreign file cannot flood the box. */
const MAX_ROWS = 50
const MAX_TEXT = 300
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f-\u009f]/g

/** One line, no control characters (an escape sequence must not reach the terminal), at most MAX_TEXT characters. */
function clean(value: unknown): string {
  if (typeof value !== 'string') return ''
  const flat = value.replace(CONTROL, ' ').split(/\s+/).filter(Boolean).join(' ')
  return flat.length <= MAX_TEXT ? flat : `${flat.slice(0, MAX_TEXT - 1)}…`
}

/**
 * The status folder (user decision 01/11/2026): an absolute PODIUM_STATUS_DIR, else `.claude/podium-status` in the home
 * folder, USERPROFILE first as Python's expanduser takes it on Windows, then HOME. '' when none is usable: a relative
 * folder would resolve against another directory here than in the script that writes it.
 */
export function statusDir(chosen?: string, profile?: string, home?: string): string {
  if (chosen) return /^([A-Za-z]:)?[\\/]/.test(chosen) ? chosen.replace(/[\\/]+$/, '') : ''
  const base = profile || home
  return base ? `${base.replace(/[\\/]+$/, '')}/.claude/podium-status` : ''
}

/** The status script beside the configuration script the pane found ('' when none was found). */
export const statusScript = (configScript: string) =>
  (configScript.endsWith('/podium_config.py') ? `${configScript.slice(0, -'podium_config.py'.length)}podium_status.py` : '')

/** What a refresh found: no file, a file and its modification time, or an error (unreadable, denied). */
export type StatusProbe = { kind: 'missing' } | { kind: 'error' } | { kind: 'file'; mtimeMs: number }

/**
 * What a refresh does, from the stamp of the last read and what it found now: `read` the file (a new modification time),
 * `clear` the box (the file went away), or `keep` it. An error keeps the box as it was and resets the stamp, so the
 * next look reads again instead of trusting an old stamp.
 */
export function statusStep(stamp: number, probe: StatusProbe): { action: 'keep' | 'clear' | 'read'; stamp: number } {
  if (probe.kind === 'error') return { action: 'keep', stamp: -1 }
  if (probe.kind === 'missing') return stamp === 0 ? { action: 'keep', stamp: 0 } : { action: 'clear', stamp: 0 }
  return probe.mtimeMs === stamp ? { action: 'keep', stamp } : { action: 'read', stamp: probe.mtimeMs }
}

/**
 * The status file as the box reads it; null for an empty, unreadable or foreign file, which the box shows as nothing
 * running. Only strings are kept: the file is written by a script, but read here as untrusted text.
 */
export function parseStatus(text: string): StatusData | null {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null
  const one = raw as Record<string, unknown>
  const rows = (Array.isArray(one.rows) ? one.rows : [])
    .filter((row): row is Record<string, unknown> => typeof row === 'object' && row !== null && !Array.isArray(row))
    .map(row => ({
      item: clean(row.item), state: clean(row.state), figure: clean(row.figure), waiting: clean(row.waiting),
      // Over 100 reads as 100, as the script stores it (F-038).
      percent: /^\d{1,3}$/.test(clean(row.percent)) ? String(Math.min(100, Number(clean(row.percent)))) : '', blocker: clean(row.blocker),
      agent: clean(row.agent), note: clean(row.note), label: clean(row.label),
    }))
  return { now: clean(one.now), next: clean(one.next), rows: trim(rows), updated: clean(one.updated), budget: clean(one.budget) }
}

/** The states of a step that is over, as podium_status_rows.py's CLOSED. */
const CLOSED = ['done', 'did not run']
/** Which row goes first past MAX_ROWS, in podium_status_rows.py's order: a finished subagent step, any other subagent
 *  step but a failed one, any subagent step, a finished step of this session, then the oldest row (F-038). */
const DROP_FIRST: Array<(row: StatusRow) => boolean> = [
  row => row.agent !== '' && CLOSED.includes(row.state), row => row.agent !== '' && row.state !== 'failed', row => row.agent !== '',
  row => CLOSED.includes(row.state), () => true,
]

/** At most MAX_ROWS, dropping the same rows as the script's trim, so a foreign file shows what the script would keep. */
export function trim(rows: StatusRow[]): StatusRow[] {
  const out = [...rows]
  while (out.length > MAX_ROWS) {
    for (const pick of DROP_FIRST) {
      const at = out.findIndex(pick)
      if (at >= 0) {
        out.splice(at, 1)
        break
      }
    }
  }
  return out
}

/** The short state words (user decision 02/11/2026), so the State column stays narrow: a state is one of these. */
const SHORT: Record<string, string> = {
  'not started': 'todo', pending: 'todo', running: 'run', 'in progress': 'run', done: 'done', blocked: 'stuck',
  'did not run': 'skip', skipped: 'skip', failed: 'fail',
}
/** The state of the step at work: the box draws it in bold. */
const RUNNING = 'run'
/** What a writer puts where it has nothing to say: the box leaves it out. */
const PLACEHOLDERS = ['', '-', '—']

// The box draws the steps only (user decision 04/11/2026): `now` and `next` stay in the file for the hooks and `show`, but
// are not drawn, so a table with no steps reads as nothing running.
const busy = (data: StatusData | null): data is StatusData => data !== null && data.rows.length > 0

/** A cap on one table column, in cells: a longer text wraps inside its column instead of pushing the next one away. */
const STATUS_COLUMN = 24

/**
 * A state as its short word and what else the writer put in it (`running: 3 of 8` -> run, `3 of 8`). A state that is
 * none of the known ones keeps no word; all of its text goes to the note.
 */
export function splitState(state: string): { short: string; detail: string } {
  const text = state.trim()
  const lower = text.toLowerCase()
  const known = Object.keys(SHORT).sort((a, b) => b.length - a.length)
    .find(word => lower === word || (lower.startsWith(word) && /^[\s:,;(-]/.test(lower.slice(word.length))))
  return known === undefined ? { short: '', detail: text } : { short: SHORT[known]!, detail: text.slice(known.length).replace(/^[\s:,;-]+/, '') }
}

/** The steps by who runs them: this session first, then each subagent in the order it first wrote. */
export function stepGroups(rows: StatusRow[]): Array<{ agent: string; rows: StatusRow[] }> {
  const agents = [...new Set(['', ...rows.map(row => row.agent)])]
  return agents.map(agent => ({ agent, rows: rows.filter(row => row.agent === agent) })).filter(group => group.rows.length > 0)
}

/** Everything a step says besides its name, state and %: the state's own detail, its note, an older row's figure. */
export function noteOf(row: StatusRow): string {
  const figure = row.percent === '' && !PLACEHOLDERS.includes(row.figure) ? row.figure : ''
  return [splitState(row.state).detail, row.note, figure].filter(text => !PLACEHOLDERS.includes(text)).join(' · ')
}

/** The folds of the Status box's accordions: one per state group (`state:<group>`) and one per agent in it (`state:<group>:<agent>`). */
export type AgentFolds = { folded: (id: FoldId) => boolean; toggle: (id: FoldId) => () => void }
/** A box with no fold state of its own: the pane's start state (Done and Skipped closed, everything else open). */
const START_FOLDS: AgentFolds = { folded: id => isFolded({}, id), toggle: () => () => undefined }

/**
 * The state groups, in the order drawn (user decision 15/11/2026: by state first, then by agent, so a long list stays
 * short): the group's fold id, its title and the short state words it holds. A state the box does not know reads as To do.
 */
export const STATE_GROUPS = [
  { id: 'run', title: 'Running', shorts: ['run'] }, { id: 'stuck', title: 'Stuck', shorts: ['stuck'] },
  { id: 'fail', title: 'Failed', shorts: ['fail'] }, { id: 'todo', title: 'To do', shorts: ['todo', ''] },
  { id: 'done', title: 'Done', shorts: ['done'] }, { id: 'skip', title: 'Skipped', shorts: ['skip'] },
] as const
export type StateGroup = (typeof STATE_GROUPS)[number]['id']

/** The steps by state group, in STATE_GROUPS' order, each in the order written; a group with no step is left out. */
export function stateGroups(rows: StatusRow[]): Array<{ id: StateGroup; title: string; rows: StatusRow[] }> {
  return STATE_GROUPS
    .map(group => ({ id: group.id, title: group.title, rows: rows.filter(row => (group.shorts as readonly string[]).includes(splitState(row.state).short)) }))
    .filter(group => group.rows.length > 0)
}

/**
 * The status box (user decisions 01/11, 02/11, 04/11 and 15/11/2026): the budget line, then one accordion per state group
 * (Running, Stuck, Failed, To do, Done, Skipped; an empty one is not drawn), each with its count; under a group one
 * accordion per agent, this session first and each subagent after it, with its count; under an agent a table of
 * step · state · % · note, a running step in bold, and under a step `-> what blocks it`. The note is one line that does
 * not wrap (the pane cannot scroll sideways, so a longer one is cut at the edge and shows whole while the pointer is on it).
 */
export function statusBody(ui: Ui, data: StatusData | null, folds: AgentFolds = START_FOLDS) {
  const { h } = ui
  // The spend line comes first, whether or not a step is open: the user follows the budget here (06/11/2026).
  const spend = data && data.budget
    ? [explained(ui, 'status-budget', h(ui.Text, { dimColor: true }, `budget: ${data.budget}`), STATUS_HELP.budget),
        helpCard(ui, 'status-budget', STATUS_HELP.budget)]
    : null
  if (!busy(data)) return spend ? h(ui.Box, { flexDirection: 'column' }, spend, h(ui.Text, { dimColor: true }, 'nothing running')) : h(ui.Text, { dimColor: true }, 'nothing running')
  const fields = (row: StatusRow) => [row.item, splitState(row.state).short, row.percent === '' ? '' : `${row.percent}%`, noteOf(row)]
  const blocker = (row: StatusRow) => (PLACEHOLDERS.includes(row.blocker || row.waiting) ? '' : `-> ${row.blocker || row.waiting}`)
  // No heading row (user decision 04/11/2026): the columns are step · state · % · note, in that order, and need no names.
  const widths = [0, 1, 2].map(at => Math.min(STATUS_COLUMN, Math.max(...data.rows.map(row => (fields(row)[at] ?? '').length))) + 1)
  const cellsOf = (texts: string[], kind: 'running' | 'plain') => h(ui.Box, { flexDirection: 'row', columnGap: 1 },
    texts.map((text, at) => h(ui.Box, at < texts.length - 1 ? { width: widths[at], flexShrink: 0 } : { flexGrow: 1, overflow: 'hidden' },
      h(ui.Text, { ...(kind === 'plain' ? (at === 0 ? {} : { dimColor: true }) : { bold: true }), ...(at === texts.length - 1 ? { wrap: 'truncate-end' } : {}) }, text))))
  // The arrow of a group or agent header presses; the rest is its label.
  const fold = (id: FoldId, label: unknown[]) => h(ui.Box, { flexDirection: 'row', columnGap: 1 },
    h(ui.Button, { key: `fold-${id}`, plain: true, onPress: folds.toggle(id) }, folds.folded(id) ? '▸' : '▾'), ...label)
  const stepRows = (agent: string, rows: StatusRow[]) => rows.map(row => {
    const cells = cellsOf(fields(row), splitState(row.state).short === RUNNING ? 'running' : 'plain')
    const id = `note-${agent}-${row.item}`
    return [
      // The row shows one line of its note; while the pointer is on the row, a card shows the whole of it.
      // A note has its (i) after the row (user decision 09/11/2026); the pointer on either shows the whole note.
      noteOf(row) === '' ? cells : explained(ui, id, cells, noteOf(row)),
      helpCard(ui, id, noteOf(row)),
      blocker(row) === '' ? null : h(ui.Box, { marginLeft: 2 }, h(ui.Text, { dimColor: true }, blocker(row)))]
  })
  // A group or agent header: the arrow presses; the bold title carries its (i) and card, its count follows it dimmed.
  const header = (id: FoldId, hover: string, title: string, card: string, count: number) => [
    fold(id, [explained(ui, hover, h(ui.Text, { bold: true }, title), card), h(ui.Text, { dimColor: true }, `(${count})`)]),
    helpCard(ui, hover, card)]
  const agentBlock = (group: StateGroup, one: { agent: string; rows: StatusRow[] }) => {
    const name = one.agent || 'this session'
    const id: FoldId = `state:${group}:${name}`
    // A subagent is titled by its label (`<description> (<model>)`) when the hooks found one; the fold keeps its id.
    const title = one.rows.find(row => row.label !== '')?.label || name
    return h(ui.Box, { flexDirection: 'column', marginLeft: INDENT },
      header(id, `status-${group}-${name}`, title, one.agent ? STATUS_HELP.subagent : STATUS_HELP.session, one.rows.length),
      folds.folded(id) ? null : h(ui.Box, { flexDirection: 'column', marginLeft: INDENT }, stepRows(name, one.rows)))
  }
  const groupBlock = (group: { id: StateGroup; title: string; rows: StatusRow[] }) => {
    const id: FoldId = `state:${group.id}`
    return h(ui.Box, { flexDirection: 'column', marginTop: 1 },
      header(id, `status-${group.id}`, group.title, STATUS_HELP[group.id], group.rows.length),
      folds.folded(id) ? null : stepGroups(group.rows).map(one => agentBlock(group.id, one)))
  }
  return h(ui.Box, { flexDirection: 'column' },
    spend, stateGroups(data.rows).map(groupBlock))
}
