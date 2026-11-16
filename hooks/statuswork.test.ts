import { expect, test } from 'claude-code/testing'

import { parseStatus, statusBody, workOf } from './status'

// Layer 3 of the Status box (user decision 16/11/2026): an agent's own work under its row, as
// scripts/podium_status_work.py writes it - entries joined by the record-separator sign, one dim line each.
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
const OPEN = { folded: () => false, toggle: () => () => undefined }
const SEP = '␞'

test('a work field reads as its entries: split, trimmed, none empty, at most six', () => {
  expect(workOf(`… 2 earlier${SEP} edited a.ts ${SEP}${SEP} ${SEP}commit 1a2b3c4 x (not verified)`))
    .toEqual(['… 2 earlier', 'edited a.ts', 'commit 1a2b3c4 x (not verified)'])
  expect(workOf(Array.from({ length: 9 }, (_, n) => `e${n}`).join(SEP))).toEqual(['e0', 'e1', 'e2', 'e3', 'e4', 'e5'])
  for (const value of ['', '   ', SEP, null, undefined, 42, ['a'], { work: 'a' }]) expect(workOf(value)).toEqual([])
})

test('a foreign work field cannot reach the terminal with control or bidirectional marks, nor flood the box', () => {
  expect(workOf('edited \u001b[31ma‮.ts')).toEqual(['edited [31ma .ts'])
  const long = workOf('x'.repeat(5000))
  expect(long.length).toBe(1)
  expect(long[0]!.length).toBe(600)
  expect(long[0]!.endsWith('…')).toBe(true)
})

test('a row gets work only where there is some, so a row without reads exactly as before', () => {
  const data = parseStatus(JSON.stringify({ rows: [
    { item: 'task', state: 'done', agent: 'podium:qa x', work: `edited a.ts${SEP}edited b.ts` },
    { item: 'task', state: 'done', agent: 'podium:dev y', work: '' },
    { item: 'plan', state: 'running' }] }))!
  expect(data.rows.map(row => row.work)).toEqual([['edited a.ts', 'edited b.ts'], undefined, undefined])
  expect(data.rows.map(row => 'work' in row)).toEqual([true, false, false])
})

test('under an agent step each entry is one dim line, cut at the edge, in order; a step with none draws no list', () => {
  const data = parseStatus(JSON.stringify({ rows: [
    { item: 'task', state: 'running', agent: 'podium:qa x', work: `… earlier${SEP}edited a.ts${SEP}commit 1234567 m` },
    { item: 'other', state: 'running', agent: 'podium:dev y' }] }))!
  const lines = all(statusBody(ui, data, OPEN), 'Text').filter(text => words(text).startsWith('· '))
  expect(lines.map(words)).toEqual(['· … earlier', '· edited a.ts', '· commit 1234567 m'])
  expect(lines.every(line => line.props.dimColor === true && line.props.wrap === 'truncate-end')).toBe(true)
  // The list sits under its own step: the step's name is drawn before the first entry and the other step after the last.
  const texts = all(statusBody(ui, data, OPEN), 'Text').map(words)
  const at = (text: string) => texts.indexOf(text)
  expect(at('task') < at('· … earlier') && at('· commit 1234567 m') < at('other')).toBe(true)
  const folded = { folded: () => true, toggle: () => () => undefined }
  expect(all(statusBody(ui, data, folded), 'Text').some(text => words(text).startsWith('· '))).toBe(false)
})
