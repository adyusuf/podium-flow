// What the Status box of the podium pane shows: this session's status table (user decision 01/11/2026), the same table
// `standards/00-working-method.md` §10 asks for in a reply during a long run. Engine-free like boxes.ts, so a test hands in
// a recording factory. The file is written by scripts/podium_status.py; register.tsx reads it and hands its text here.
import type { FoldId, Ui } from './boxes'
import { helpCard, hoverable, INDENT } from './controls'
import { STATUS_HELP } from './help'

/** A step (user decision 02/11/2026): `percent` done ('' when not given), `blocker`, and `agent` ('' = this session). */
type StatusRow = { item: string; state: string; figure: string; waiting: string; percent: string; blocker: string; agent: string; note: string }
export type StatusData = { now: string; next: string; rows: StatusRow[]; updated: string }

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
    .slice(-MAX_ROWS)
    .map(row => ({
      item: clean(row.item), state: clean(row.state), figure: clean(row.figure), waiting: clean(row.waiting),
      percent: /^\d{1,3}$/.test(clean(row.percent)) ? clean(row.percent) : '', blocker: clean(row.blocker), agent: clean(row.agent),
      note: clean(row.note),
    }))
  return { now: clean(one.now), next: clean(one.next), rows, updated: clean(one.updated) }
}

/** The short state words (user decision 02/11/2026), so the State column stays narrow: a state is one of these. */
const SHORT: Record<string, string> = {
  'not started': 'todo', pending: 'todo', running: 'run', 'in progress': 'run', done: 'done', blocked: 'stuck',
  'did not run': 'skip', skipped: 'skip',
}
/** The state of the step at work: the box draws it in bold. */
const RUNNING = 'run'
/** What a writer puts where it has nothing to say: the box leaves it out. */
const PLACEHOLDERS = ['', '-', '—']

const busy = (data: StatusData | null): data is StatusData =>
  data !== null && (data.now !== '' || data.next !== '' || data.rows.length > 0)

/** A cap on one table column, in cells: a longer text wraps inside its column instead of pushing the next one away. */
const STATUS_COLUMN = 36

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

/** How much of a group of steps is done: the mean of the steps that give a percentage, or '' when none does. */
export function donePercent(rows: StatusRow[]): string {
  const given = rows.filter(row => row.percent !== '').map(row => Number(row.percent))
  return given.length === 0 ? '' : `${Math.round(given.reduce((sum, one) => sum + one, 0) / given.length)}%`
}

/** A group's state: run while one of its steps runs, else stuck while one is blocked, done when all are over, else todo. */
export function groupState(rows: StatusRow[]): string {
  const shorts = rows.map(row => splitState(row.state).short)
  if (shorts.includes(RUNNING)) return RUNNING
  if (shorts.includes('stuck')) return 'stuck'
  return shorts.every(short => short === 'done' || short === 'skip') ? 'done' : 'todo'
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

/** The folds of the Status box's accordions: one per agent, and its To do and Completed branches under it. */
export type AgentFolds = { folded: (id: FoldId) => boolean; toggle: (id: FoldId) => () => void }
/** A box with no fold state of its own: every agent open, every Completed branch closed (the start state of the pane). */
const START_FOLDS: AgentFolds = { folded: id => id.endsWith(':done'), toggle: () => () => undefined }

/** The state words of a step that is over; every other step (todo, run, stuck, or a state this box does not know) is still to do. */
const OVER = ['done', 'skip']
/** A group's steps split into those still to do (the one running among them) and those over, each in the order written. */
export function splitSteps(rows: StatusRow[]): { todo: StatusRow[]; done: StatusRow[] } {
  const over = (row: StatusRow) => OVER.includes(splitState(row.state).short)
  return { todo: rows.filter(row => !over(row)), done: rows.filter(over) }
}

/**
 * The status box (user decisions 01/11, 02/11 and 04/11/2026): what runs now and next, then one accordion per agent, this
 * session first and each subagent after it, named in bold with its state and %. Under an agent two branches: To do (what
 * runs and what runs next, open) and Completed (closed at start), each a table of step · state · % · note, a running step in
 * bold; under a step, `-> what blocks it`. The note is one line that does not wrap (the pane cannot scroll sideways, so a
 * longer one is cut at the edge and shows whole while the pointer is on it).
 */
export function statusBody(ui: Ui, data: StatusData | null, folds: AgentFolds = START_FOLDS) {
  const { h } = ui
  if (!busy(data)) return h(ui.Text, { dimColor: true }, 'nothing running')
  const heads = ['Step', 'State', '%', 'Note']
  const fields = (row: StatusRow) => [row.item, splitState(row.state).short, row.percent === '' ? '' : `${row.percent}%`, noteOf(row)]
  const blocker = (row: StatusRow) => (PLACEHOLDERS.includes(row.blocker || row.waiting) ? '' : `-> ${row.blocker || row.waiting}`)
  const widths = heads.map((head, at) =>
    Math.min(STATUS_COLUMN, Math.max(head.length, ...data.rows.map(row => (fields(row)[at] ?? '').length))) + 1)
  const cellsOf = (texts: string[], kind: 'head' | 'running' | 'plain') => h(ui.Box, { flexDirection: 'row', columnGap: 1 },
    texts.map((text, at) => h(ui.Box, at < texts.length - 1 ? { width: widths[at], flexShrink: 0 } : { flexGrow: 1, overflow: 'hidden' },
      kind === 'head' ? hoverable(ui, `status-${text}`, h(ui.Text, { bold: true }, text))
        : h(ui.Text, { ...(kind === 'plain' ? (at === 0 ? {} : { dimColor: true }) : { bold: true }), ...(at === texts.length - 1 ? { wrap: 'truncate-end' } : {}) }, text))))
  const said = (title: string, text: string) => (text === ''
    ? null
    : [h(ui.Box, { flexDirection: 'row', columnGap: 1 },
      h(ui.Box, { minWidth: 6, flexShrink: 0 }, hoverable(ui, `status-${title}`, h(ui.Text, { bold: true }, title))), h(ui.Text, {}, text)),
    helpCard(ui, `status-${title}`, STATUS_HELP[title])])
  // A branch header or an agent header: the arrow presses, the rest is its label.
  const fold = (id: FoldId, label: unknown[]) => h(ui.Box, { flexDirection: 'row', columnGap: 1 },
    h(ui.Button, { key: `fold-${id}`, plain: true, onPress: folds.toggle(id) }, folds.folded(id) ? '▸' : '▾'), ...label)
  const stepRows = (agent: string, rows: StatusRow[]) => rows.map(row => {
    const cells = cellsOf(fields(row), splitState(row.state).short === RUNNING ? 'running' : 'plain')
    const id = `note-${agent}-${row.item}`
    return [
      // The row shows one line of its note; while the pointer is on the row, a card shows the whole of it.
      noteOf(row) === '' ? cells : hoverable(ui, id, cells),
      helpCard(ui, id, noteOf(row)),
      blocker(row) === '' ? null : h(ui.Box, { marginLeft: 2 }, h(ui.Text, { dimColor: true }, blocker(row)))]
  })
  const branch = (agent: string, kind: 'todo' | 'done', rows: StatusRow[]) => {
    const id: FoldId = `agent:${agent}:${kind}`
    return rows.length === 0 ? null : h(ui.Box, { flexDirection: 'column', marginLeft: INDENT },
      fold(id, [h(ui.Text, { bold: true }, kind === 'todo' ? 'To do' : 'Completed'), h(ui.Text, { dimColor: true }, `(${rows.length})`)]),
      folds.folded(id) ? null : h(ui.Box, { flexDirection: 'column', marginLeft: INDENT }, stepRows(agent, rows)))
  }
  const accordion = (group: { agent: string; rows: StatusRow[] }) => {
    const name = group.agent || 'this session'
    const id: FoldId = `agent:${name}`
    const { todo, done } = splitSteps(group.rows)
    return h(ui.Box, { flexDirection: 'column', marginTop: 1 },
      fold(id, [h(ui.Text, { bold: true }, name), h(ui.Text, { dimColor: true }, [groupState(group.rows), donePercent(group.rows)].filter(Boolean).join(' · '))]),
      folds.folded(id) ? null : [branch(name, 'todo', todo), branch(name, 'done', done)])
  }
  return h(ui.Box, { flexDirection: 'column' },
    said('Now', data.now),
    said('Next', data.next),
    data.rows.length === 0 ? null : h(ui.Box, { flexDirection: 'column', marginTop: 1 },
      // Rows sit two branches in (agent, then To do or Completed), so the header starts there too and the columns line up.
      h(ui.Box, { marginLeft: INDENT * 2 }, cellsOf(heads, 'head')),
      heads.map(head => helpCard(ui, `status-${head}`, STATUS_HELP[head])),
      stepGroups(data.rows).map(accordion)))
}
