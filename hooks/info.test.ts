import { expect, test } from 'claude-code/testing'

import { settingsBody } from './boxes'
import { STATUS_HELP } from './help'
import { parseStatus, statusBody } from './status'

// The (i) on every label and a stored value the pane no longer offers (user decision and qa, 09/11/2026). A recording
// factory lets the tests read what would be drawn.
type Node = { type: unknown; props: Record<string, any>; children: unknown[] }
const h = (type: unknown, props: Record<string, unknown> | null, ...children: unknown[]): Node => ({ type, props: props ?? {}, children })
const ui = { h, Box: 'Box', Text: 'Text', Button: 'Button' }

function flat(items: unknown[]): unknown[] {
  return items.flatMap(item => (Array.isArray(item) ? flat(item) : item === null || item === '' ? [] : [item]))
}
function all(node: unknown, type: string): Node[] {
  if (typeof node !== 'object' || node === null) return []
  const one = node as Node
  return (one.type === type ? [one] : []).concat(...flat(one.children).map(child => all(child, type)))
}
function words(node: unknown): string {
  if (typeof node === 'string') return node
  if (typeof node !== 'object' || node === null) return ''
  return flat((node as Node).children).map(words).join('')
}
const cards = (body: unknown) => all(body, 'Box').filter(node => node.props.display === 'none').map(words)

const budget = { key: 'budget.session_usd', type: 'enum' as const, label: 'Session budget', group: 'Session',
  options: ['none', '200', '500', '1000'], legacy: ['25', '50', '100'] }
const data = (value: string) => ({ schema: [budget], values: { 'budget.session_usd': value }, sources: {}, agents: [] })
const chosen = (body: unknown) => all(body, 'Button').filter(node => node.props.dimColor === false).map(words)

test('a budget a file written before holds (100) is drawn as one more option, chosen; an offered one adds nothing', () => {
  const old = settingsBody(ui, data('100'), '', [], () => undefined)
  expect(all(old, 'Button').filter(node => String(node.props.key).startsWith('session/budget')).map(words))
    .toEqual(['none', '200', '500', '1000', '[100]'])
  expect(chosen(old)).toContain('[100]')
  const now = settingsBody(ui, data('500'), '', [], () => undefined)
  expect(all(now, 'Button').filter(node => String(node.props.key).startsWith('session/budget')).map(words))
    .toEqual(['none', '200', '[500]', '1000'])
})

test('the Status labels carry an (i) and a card: the budget line, the agent, its branches, a step with a note', () => {
  const body = statusBody(ui, parseStatus(JSON.stringify({
    budget: '$1.00 spent of $200', rows: [{ item: 'a', state: 'running', note: 'a note' }, { item: 'b', state: 'done', agent: 'podium:qa x' }],
  })))
  const drawn = all(body, 'Text').filter(node => node.props.color !== 'inverseText').map(words)
  // budget; this session, its To do, the noted step; the qa agent, its Completed.
  expect(drawn.filter(text => text === '(i)').length).toBe(6)
  for (const text of [STATUS_HELP.budget, STATUS_HELP.session, STATUS_HELP.subagent, STATUS_HELP.todo, STATUS_HELP.done, 'a note']) {
    expect(cards(body)).toContain(text)
  }
})
