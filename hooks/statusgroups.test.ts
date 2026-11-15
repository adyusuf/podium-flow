import { expect, test } from 'claude-code/testing'

import { FOLDED_AT_START, isFolded } from './boxes'
import { STATUS_HELP } from './help'
import { parseStatus, STATE_GROUPS, stateGroups, statusBody } from './status'

// The Status box by state first, then by agent (user decision 15/11/2026), drawn with a recording factory.
type Node = { type: unknown; props: Record<string, any>; children: unknown[] }
const h = (type: unknown, props: Record<string, unknown> | null, ...children: unknown[]): Node => ({ type, props: props ?? {}, children })
const ui = { h, Box: 'Box', Text: 'Text', Button: 'Button' }
const flat = (items: unknown[]): unknown[] => items.flatMap(item => (Array.isArray(item) ? flat(item) : item === null || item === '' ? [] : [item]))
function all(node: unknown, type: string): Node[] {
  if (typeof node !== 'object' || node === null) return []
  const one = node as Node
  return (one.type === type ? [one] : []).concat(...flat(one.children).map(child => all(child, type)))
}
const words = (node: unknown): string =>
  (typeof node === 'string' ? node : typeof node === 'object' && node !== null ? flat((node as Node).children).map(words).join('') : '')
const shown = (node: unknown) => all(node, 'Text').filter(text => text.props.color !== 'inverseText').map(words)
const table = (rows: Array<Record<string, string>>) => parseStatus(JSON.stringify({ rows }))!
// Every group and agent open, so every header and step is drawn.
const OPEN = { folded: () => false, toggle: () => () => undefined }

const EVERY = table([
  { item: 'k', state: 'skipped' }, { item: 'd', state: 'done' }, { item: 't', state: 'not started' }, { item: 'f', state: 'failed' },
  { item: 's', state: 'blocked' }, { item: 'r', state: 'running' }, { item: 'u', state: 'gate running' },
])

test('the groups are Running, Stuck, Failed, To do, Done, Skipped, in that order, each with its count', () => {
  expect(STATE_GROUPS.map(group => group.title)).toEqual(['Running', 'Stuck', 'Failed', 'To do', 'Done', 'Skipped'])
  expect(stateGroups(EVERY.rows).map(group => [group.id, group.rows.map(row => row.item)])).toEqual([
    ['run', ['r']], ['stuck', ['s']], ['fail', ['f']], ['todo', ['t', 'u']], ['done', ['d']], ['skip', ['k']]])
  const titles = shown(statusBody(ui, EVERY, OPEN))
  const heads = STATE_GROUPS.map(group => titles.indexOf(group.title))
  expect(heads.every((at, n) => at >= 0 && (n === 0 || at > heads[n - 1]!))).toBe(true)
  expect(titles[titles.indexOf('To do') + 2]).toBe('(2)')
})

test('a state the box does not know goes to To do; a group with no step is not drawn', () => {
  const odd = table([{ item: 'x', state: 'gate running' }, { item: 'y', state: '' }, { item: 'z', state: 'done' }])
  expect(stateGroups(odd.rows).map(group => [group.id, group.rows.length])).toEqual([['todo', 2], ['done', 1]])
  const titles = shown(statusBody(ui, odd, OPEN))
  expect(['Running', 'Stuck', 'Failed', 'Skipped'].filter(title => titles.includes(title))).toEqual([])
})

test('inside a group each agent has its own accordion with its count, this session first', () => {
  const data = table([
    { item: 'a', state: 'running', agent: 'podium:qa x' }, { item: 'b', state: 'running' }, { item: 'c', state: 'running', agent: 'podium:qa x' },
    { item: 'd', state: 'done', agent: 'podium:dev y' },
  ])
  expect(shown(statusBody(ui, data, OPEN)).filter(text => !['(i)', 'run', '', 'done'].includes(text))).toEqual([
    'Running', '(3)', 'this session', '(1)', 'b', 'podium:qa x', '(2)', 'a', 'c', 'Done', '(1)', 'podium:dev y', '(1)', 'd'])
})

test('at start Running, Stuck, Failed and To do are open and Done and Skipped closed; the agents in a group are open', () => {
  const start = (id: string) => isFolded({}, id as never)
  expect(['state:run', 'state:stuck', 'state:fail', 'state:todo', 'state:done', 'state:skip'].map(start)).toEqual([false, false, false, false, true, true])
  expect(['state:done:this session', 'state:run:podium:qa x', 'state:skip:done'].map(start)).toEqual([false, false, false])
  // A fold state saved by the older layout (agent ids) is read without trouble; the new ids start as above.
  const older = { ...FOLDED_AT_START, 'agent:this session': true, 'agent:this session:done': false }
  expect([isFolded(older, 'state:run'), isFolded(older, 'state:done')]).toEqual([false, true])
  const buttons = all(statusBody(ui, EVERY), 'Button')
  expect(buttons.map(button => [String(button.props.key).slice('fold-'.length), words(button)])).toEqual([
    ['state:run', '▾'], ['state:run:this session', '▾'], ['state:stuck', '▾'], ['state:stuck:this session', '▾'], ['state:fail', '▾'],
    ['state:fail:this session', '▾'], ['state:todo', '▾'], ['state:todo:this session', '▾'], ['state:done', '▸'], ['state:skip', '▸']])
})

test('a group header has an (i) and a card saying what it holds; an agent header keeps its card', () => {
  const body = statusBody(ui, table([{ item: 'a', state: 'blocked' }, { item: 'b', state: 'blocked', agent: 'podium:qa x' }]), OPEN)
  const cards = all(body, 'Box').filter(node => node.props.hover?.display === 'flex').map(words)
  expect([STATUS_HELP.stuck, STATUS_HELP.session, STATUS_HELP.subagent].every(card => cards.includes(card))).toBe(true)
  for (const group of STATE_GROUPS) expect(STATUS_HELP[group.id].length > 0).toBe(true)
})

test('a subagent is titled by its label, <description> (<model>), and keeps its fold id (layer 2, 16/11/2026)', () => {
  const data = table([
    { item: 'task', state: 'running', agent: 'podium:qa ae234b', label: 'QA review of ti-batch (Sonnet 5.5)' },
    { item: 'task', state: 'done', agent: 'podium:dev a849d9' },
  ])
  const titles = shown(statusBody(ui, data, OPEN))
  expect(titles.includes('QA review of ti-batch (Sonnet 5.5)')).toBe(true)
  expect(titles.includes('podium:qa ae234b')).toBe(false)
  expect(titles.includes('podium:dev a849d9')).toBe(true)          // no label: the agent's name, as before
  const keys = all(statusBody(ui, data, OPEN), 'Button').map(button => String(button.props.key))
  expect(keys.includes('fold-state:run:podium:qa ae234b')).toBe(true)
})
