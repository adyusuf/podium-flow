import { expect, test } from 'claude-code/testing'

import { donePercent, groupState, noteOf, parseStatus, splitState, statusBody, stepGroups, statusDir, statusScript, statusStep } from './status'

// A recording factory: an element is { type, props, children }, so the tests read what the box would draw.
type Node = { type: unknown; props: Record<string, any>; children: unknown[] }
const h = (type: unknown, props: Record<string, unknown> | null, ...children: unknown[]): Node => ({ type, props: props ?? {}, children })
const ui = { h, Box: 'Box', Text: 'Text', Button: 'Button' }

function flat(items: unknown[]): unknown[] {
  return items.flatMap(item => (Array.isArray(item) ? flat(item) : item === null || item === '' ? [] : [item]))
}
function all(node: unknown, type: string): Node[] {
  if (typeof node !== 'object' || node === null) return []
  const one = node as Node
  const here = one.type === type ? [one] : []
  return here.concat(...flat(one.children).map(child => all(child, type)))
}
function words(node: unknown): string {
  if (typeof node === 'string') return node
  if (typeof node !== 'object' || node === null) return ''
  return flat((node as Node).children).map(words).join('')
}

const FILE = JSON.stringify({
  now: 'prod gate', next: 'plugin update', updated: '2026-11-01T18:00:00Z',
  rows: [
    { item: 'dev', state: 'pushed', figure: '4a45bda (promote.log)', waiting: '—' },
    { item: 'prod', state: 'gate running', figure: 'coverage step (gate-prod.log)', waiting: 'promote.sh' },
  ],
})

test('the status file is read as text: only strings are kept, anything else is nothing running', () => {
  expect(parseStatus(FILE)?.rows.length).toBe(2)
  expect(parseStatus('not json')).toBe(null)
  expect(parseStatus('[1, 2]')).toBe(null)
  expect(parseStatus('null')).toBe(null)
  const odd = parseStatus(JSON.stringify({ now: 5, rows: [{ item: 'a', state: 1 }, 'x', null] }))
  expect(odd).toEqual({ now: '', next: '', updated: '', rows: [{ item: 'a', state: '', figure: '', waiting: '', percent: '', blocker: '', agent: '', note: '' }] })
  // A percentage is digits only; anything else reads as not given.
  expect(parseStatus(JSON.stringify({ rows: [{ item: 'a', percent: '45' }, { item: 'b', percent: '45%' }, { item: 'c', percent: 7 }] }))!.rows.map(row => row.percent)).toEqual(['45', '', ''])
})

test('the body shows now and next, then step · state · % · note, a short state, -> blocker under the step', () => {
  const lines = (body: unknown) => all(body, 'Box').filter(node => node.props.flexDirection === 'row' && !node.props.marginLeft)
    .map(node => all(node, 'Text').map(words).join(' | '))
  const body = statusBody(ui, parseStatus(FILE))
  // An older row: its state has no short word, so the whole state goes to the note with the measured figure.
  expect(lines(body)).toEqual(['Now | prod gate', 'Next | plugin update', 'Step | State | % | Note',
    'dev |  |  | pushed · 4a45bda (promote.log)', 'prod |  |  | gate running · coverage step (gate-prod.log)'])
  expect(all(body, 'Box').filter(node => node.props.marginLeft === 2).map(words)).toEqual(['-> promote.sh'])
  const steps = statusBody(ui, parseStatus(JSON.stringify({ rows: [
    { item: '1. data', state: 'done', percent: '100' },
    { item: '2. pane', state: 'running: 3 of 8 files', percent: '40', blocker: 'qa review', note: 'tabs first' }] })))
  expect(lines(steps).slice(1)).toEqual(['1. data | done | 100% | ', '2. pane | run | 40% | 3 of 8 files · tabs first'])
  expect(all(steps, 'Text').filter(node => node.props.bold).map(words)).toEqual(['Step', 'State', '%', 'Note', '2. pane', 'run', '40%', '3 of 8 files · tabs first'])
  expect(all(steps, 'Box').filter(node => node.props.marginLeft === 2).map(words)).toEqual(['-> qa review'])
})

test('the columns have one width on every row, capped so a long text wraps inside its column; the note column takes the rest', () => {
  const long = 'x'.repeat(80)
  const body = statusBody(ui, parseStatus(JSON.stringify({ rows: [{ item: long, state: 'done', percent: '100', note: 'n' }] })))
  const rows = all(body, 'Box').filter(node => node.props.flexDirection === 'row')
  const widths = rows.map(row => flat(row.children).map(cell => (cell as Node).props.width))
  expect(widths).toEqual([[37, 6, 5, undefined], [37, 6, 5, undefined]])
})

test('an empty table, or none, says nothing running', () => {
  expect(words(statusBody(ui, null))).toBe('nothing running')
  expect(words(statusBody(ui, parseStatus('{"now": "", "rows": []}')))).toBe('nothing running')
  const onlyNow = statusBody(ui, parseStatus('{"now": "tests"}'))
  expect(all(onlyNow, 'Text').filter(node => node.props.color !== 'inverseText').map(words)).toEqual(['Now', 'tests'])
})

test('the file is untrusted text: control characters go, each field is one capped line, rows are capped at 50', () => {
  const data = parseStatus(JSON.stringify({ now: 'a\u001b[2Jb\u0007c\u009bd', next: 'x'.repeat(400),
    rows: Array.from({ length: 55 }, (_, at) => ({ item: `i${at}` })).concat([[1, 2] as never]) }))!
  expect(data.now).toBe('a [2Jb c d')
  expect(data.next.length).toBe(300)
  expect(data.next.endsWith('…')).toBe(true)
  expect([data.rows.length, data.rows[0]!.item, data.rows[49]!.item]).toEqual([50, 'i5', 'i54'])
})

test('a refresh reads on a new modification time, keeps on the same one, clears once when the file goes', () => {
  expect(statusStep(-1, { kind: 'file', mtimeMs: 5 })).toEqual({ action: 'read', stamp: 5 })
  expect(statusStep(5, { kind: 'file', mtimeMs: 5 })).toEqual({ action: 'keep', stamp: 5 })
  expect(statusStep(5, { kind: 'file', mtimeMs: 6 })).toEqual({ action: 'read', stamp: 6 })
  expect(statusStep(5, { kind: 'missing' })).toEqual({ action: 'clear', stamp: 0 })
  expect(statusStep(-1, { kind: 'missing' })).toEqual({ action: 'clear', stamp: 0 })
  expect(statusStep(0, { kind: 'missing' })).toEqual({ action: 'keep', stamp: 0 })
})

test('an error keeps the table and resets the stamp, so the next look reads again', () => {
  expect(statusStep(5, { kind: 'error' })).toEqual({ action: 'keep', stamp: -1 })
  expect(statusStep(0, { kind: 'error' })).toEqual({ action: 'keep', stamp: -1 })
  expect(statusStep(-1, { kind: 'file', mtimeMs: 5 }).action).toBe('read')
})

test('the folder: an absolute PODIUM_STATUS_DIR, else USERPROFILE, else HOME; nothing usable gives none', () => {
  expect(statusDir('/tmp/st/', 'C:\\Users\\u', '/home/u')).toBe('/tmp/st')
  expect(statusDir('D:\\st', undefined, '/home/u')).toBe('D:\\st')
  expect(statusDir('relative/dir', undefined, '/home/u')).toBe('')
  expect(statusDir(undefined, 'C:\\Users\\u', '/home/u')).toBe('C:\\Users\\u/.claude/podium-status')
  expect(statusDir(undefined, undefined, '/home/u/')).toBe('/home/u/.claude/podium-status')
  expect(statusDir('', '', '')).toBe('')
  expect(statusDir(undefined, undefined, undefined)).toBe('')
})

test('the status script sits beside the configuration script the pane found; none found, none run', () => {
  expect(statusScript('/cache/podium/1a2b/scripts/podium_config.py')).toBe('/cache/podium/1a2b/scripts/podium_status.py')
  expect(statusScript('')).toBe('')
  expect(statusScript('/elsewhere/other.py')).toBe('')
})

test('steps group by who runs them, this session first; each group opens with a divider and a bold row with its state and %', () => {
  const data = parseStatus(JSON.stringify({ rows: [
    { item: '1. plan', state: 'done', percent: '100' }, { item: 'review', state: 'running', percent: '50', agent: 'qa a9f3c2' },
    { item: '2. build', state: 'running', percent: '20' }, { item: 'scan', state: 'not started', percent: '0', agent: 'qa a9f3c2' }] }))!
  expect(stepGroups(data.rows).map(group => [group.agent, group.rows.map(row => row.item)])).toEqual([
    ['', ['1. plan', '2. build']], ['qa a9f3c2', ['review', 'scan']]])
  expect([donePercent(data.rows.slice(0, 1)), donePercent([]), donePercent(stepGroups(data.rows)[1]!.rows)]).toEqual(['100%', '', '25%'])
  // The mean is rounded, not cut (62.5 -> 63); this session's group comes first even when a subagent wrote first.
  const half = parseStatus(JSON.stringify({ rows: [{ item: 'a', agent: 'qa x', percent: '50' }, { item: 'b', agent: 'qa x', percent: '75' }, { item: 'c', percent: '0' }] }))!
  expect(donePercent(half.rows.slice(0, 2))).toBe('63%')
  expect(stepGroups(half.rows).map(group => group.agent)).toEqual(['', 'qa x'])
  const body = statusBody(ui, data)
  const groupRows = all(body, 'Box').filter(node => node.props.flexDirection === 'row')
    .map(node => all(node, 'Text')).filter(texts => texts.length === 4 && texts.every(text => text.props.bold) && words(texts[0]) !== 'Step')
    .map(texts => texts.map(words).join(' | '))
  expect(groupRows.filter(row => row.startsWith('this session') || row.startsWith('qa a9f3c2 |'))).toEqual(['this session | run | 60% | ', 'qa a9f3c2 | run | 25% | '])
  expect(all(body, 'Box').filter(node => node.props.borderTop === true && node.props.borderBottom === false).length).toBe(2)
  // With this session's steps alone, no group row and no divider.
  const alone = statusBody(ui, parseStatus(JSON.stringify({ rows: [{ item: '1. plan', state: 'done', percent: '100' }] })))
  expect(all(alone, 'Text').some(node => words(node) === 'this session')).toBe(false)
  expect(all(alone, 'Box').some(node => node.props.borderTop === true)).toBe(false)
})

test('a state is a short word and its detail; a group runs while a step runs, is stuck while one is blocked, else done or todo', () => {
  expect(['not started', 'running', 'done', 'blocked', 'did not run', 'in progress', 'pending'].map(state => splitState(state).short))
    .toEqual(['todo', 'run', 'done', 'stuck', 'skip', 'run', 'todo'])
  expect(splitState('running: 3 of 8')).toEqual({ short: 'run', detail: '3 of 8' })
  expect(splitState('blocked (approval)')).toEqual({ short: 'stuck', detail: '(approval)' })
  expect(splitState('gate running')).toEqual({ short: '', detail: 'gate running' })
  expect(splitState('doneish')).toEqual({ short: '', detail: 'doneish' })
  const row = (state: string) => ({ item: 'x', state, figure: '', waiting: '', percent: '', blocker: '', agent: '', note: '' })
  expect(groupState([row('done'), row('running')])).toBe('run')
  expect(groupState([row('done'), row('blocked')])).toBe('stuck')
  expect(groupState([row('done'), row('did not run')])).toBe('done')
  expect(groupState([row('done'), row('not started')])).toBe('todo')
  expect(noteOf({ ...row('running: half'), note: 'n', figure: '3/8' })).toBe('half · n · 3/8')
  expect(noteOf({ ...row('done'), percent: '100', figure: '100%' })).toBe('')
})
