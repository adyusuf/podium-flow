// What the Status box of the podium pane shows: this session's status table (user decision 01/11/2026), the same table
// `standards/00-working-method.md` §10 asks for in a reply during a long run. Engine-free like boxes.ts, so a test hands in
// a recording factory. The file is written by scripts/podium_status.py; register.tsx reads it and hands its text here.
import type { Ui } from './boxes'
import { helpCard, hoverable } from './controls'
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

/**
 * The status box (user decisions 01/11 and 02/11/2026): what runs now and next, then the steps under step · state · % ·
 * note, a running step in bold. State is a short word, % sits right after it, and the note column at the end holds every
 * other explanation. Under a step: `-> what blocks it`. With subagents, each group (this session first) opens with a
 * divider and a bold row naming it, with its own state and %.
 */
export function statusBody(ui: Ui, data: StatusData | null) {
  const { h } = ui
  if (!busy(data)) return h(ui.Text, { dimColor: true }, 'nothing running')
  const heads = ['Step', 'State', '%', 'Note']
  const fields = (row: StatusRow) => [row.item, splitState(row.state).short, row.percent === '' ? '' : `${row.percent}%`, noteOf(row)]
  const blocker = (row: StatusRow) => (PLACEHOLDERS.includes(row.blocker || row.waiting) ? '' : `-> ${row.blocker || row.waiting}`)
  const widths = heads.map((head, at) =>
    Math.min(STATUS_COLUMN, Math.max(head.length, ...data.rows.map(row => (fields(row)[at] ?? '').length))) + 1)
  const cellsOf = (texts: string[], kind: 'head' | 'group' | 'running' | 'plain') => h(ui.Box, { flexDirection: 'row', columnGap: 1 },
    texts.map((text, at) => h(ui.Box, at < texts.length - 1 ? { width: widths[at], flexShrink: 0 } : { flexGrow: 1 },
      kind === 'head' ? hoverable(ui, `status-${text}`, h(ui.Text, { bold: true }, text))
        : h(ui.Text, kind === 'plain' ? (at === 0 ? {} : { dimColor: true }) : { bold: true }, text))))
  const said = (title: string, text: string) => (text === ''
    ? null
    : [h(ui.Box, { flexDirection: 'row', columnGap: 1 },
      h(ui.Box, { minWidth: 6, flexShrink: 0 }, hoverable(ui, `status-${title}`, h(ui.Text, { bold: true }, title))), h(ui.Text, {}, text)),
    helpCard(ui, `status-${title}`, STATUS_HELP[title])])
  const groups = stepGroups(data.rows)
  const titled = groups.some(group => group.agent !== '')
  // A divider: a box with only its top border, as wide as the table.
  const divider = () => h(ui.Box, { borderStyle: 'single', borderTop: true, borderBottom: false, borderLeft: false, borderRight: false, borderDimColor: true })
  return h(ui.Box, { flexDirection: 'column' },
    said('Now', data.now),
    said('Next', data.next),
    data.rows.length === 0 ? null : h(ui.Box, { flexDirection: 'column', marginTop: 1 },
      cellsOf(heads, 'head'),
      heads.map(head => helpCard(ui, `status-${head}`, STATUS_HELP[head])),
      groups.map(group => [
        titled ? [divider(), cellsOf([group.agent || 'this session', groupState(group.rows), donePercent(group.rows), ''], 'group')] : null,
        group.rows.map(row => [cellsOf(fields(row), splitState(row.state).short === RUNNING ? 'running' : 'plain'),
          blocker(row) === '' ? null : h(ui.Box, { marginLeft: 2 }, h(ui.Text, { dimColor: true }, blocker(row)))])])))
}
