import { expect, test } from 'claude-code/testing'

import { agentsBody } from './boxes'

// The Agents box drawn with a recording factory (boxes.test.ts holds the rest of its drawing and is past 300 lines).
type Node = { type: unknown; props: Record<string, any>; children: unknown[] }
const h = (type: unknown, props: Record<string, unknown> | null, ...children: unknown[]): Node => ({ type, props: props ?? {}, children })
const ui = { h, Box: 'Box', Text: 'Text', Button: 'Button' }
const flat = (items: unknown[]): unknown[] => items.flatMap(item => (Array.isArray(item) ? flat(item) : item === null || item === '' ? [] : [item]))
function buttons(node: unknown): Node[] {
  if (typeof node !== 'object' || node === null) return []
  const one = node as Node
  return (one.type === 'Button' ? [one] : []).concat(...flat(one.children).map(buttons))
}
const data = (mode: string) => ({
  schema: [], values: { mode, mode_model: 'sonnet' }, sources: {},
  // A role drawn as on in mode A (an older script, a hand-edited answer): its model radios are drawn and pressable.
  agents: [{ role: 'qa', defined: 'opus', runs_on: 'sonnet', default_model: 'sonnet', active: true, in_mode: true, enabled: 'on', model: 'default' }],
})

test('a model press in mode A is ignored like a role press: mode A runs no agents, so the setting would do nothing (F-034)', () => {
  const calls: string[][] = []
  for (const button of buttons(agentsBody(ui, data('A'), (key, value) => { calls.push([key, value]) }))) button.props.onPress()
  expect(calls).toEqual([])
  for (const button of buttons(agentsBody(ui, data('C'), (key, value) => { calls.push([key, value]) }))) button.props.onPress()
  expect(calls.map(([key]) => key)).toEqual(['agents.qa.enabled', 'agents.qa.model', 'agents.qa.model', 'agents.qa.model', 'agents.qa.model'])
})
