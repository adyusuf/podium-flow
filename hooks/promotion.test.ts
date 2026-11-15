import { expect, test } from 'claude-code/testing'

import { promotionBody } from './boxes'

// The Promotion box drawn with a recording factory (boxes.test.ts holds the rest of its drawing and is past 300 lines).
type Node = { type: unknown; props: Record<string, any>; children: unknown[] }
const h = (type: unknown, props: Record<string, unknown> | null, ...children: unknown[]): Node => ({ type, props: props ?? {}, children })
const ui = { h, Box: 'Box', Text: 'Text', Button: 'Button' }
const flat = (items: unknown[]): unknown[] => items.flatMap(item => (Array.isArray(item) ? flat(item) : item === null || item === '' ? [] : [item]))
function texts(node: unknown): Node[] {
  if (typeof node !== 'object' || node === null) return []
  const one = node as Node
  return (one.type === 'Text' ? [one] : []).concat(...flat(one.children).map(texts))
}
const words = (node: Node): string => flat(node.children).map(child => (typeof child === 'string' ? child : words(child as Node))).join('')

test('a stage git could not read says so in orange, with no "pushed" and no "no waived gate" line (F-035)', () => {
  const body = promotionBody(ui, { stages: [
    { branch: 'dev', origin: 'aaa1111', unpushed: 0, waived: [] },
    { branch: 'test', origin: '', unpushed: 0, waived: [], unreadable: 'git log failed: fatal: bad range' },
  ] })
  const shown = texts(body).filter(text => text.props.color !== 'inverseText')
  const line = shown.find(text => words(text).startsWith('test'))!
  expect(words(line)).toBe('test  could not read: git log failed: fatal: bad range')
  expect(line.props.color).toBe('#E07B00')
  expect(shown.map(words).filter(text => text === 'no waived gate on the way in').length).toBe(1)
  expect(shown.map(words).filter(text => text.endsWith('pushed')).length).toBe(1)
})
