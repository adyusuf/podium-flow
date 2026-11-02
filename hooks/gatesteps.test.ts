import { expect, test } from 'claude-code/testing'

import { FOLDED_AT_START, headWidth, isFolded, ROW_LABELS, settingsBody, settingsFolds } from './boxes'
import { gatedTargets, gateSteps, pressStep, STEP_INDENT, stepOn, stepsWidth } from './gatesteps'
import { LOCKED_STEP_HELP, ROW_HELP, STEP_HELP } from './help'

// The gate's steps under Gates (user decision 02/11/2026), read through a recording factory as in boxes.test.ts.
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
// The settings lines (a row whose first child is the head column) as [label indent, what they read].
function lines(body: unknown): Array<[number, string]> {
  return all(body, 'Box')
    .filter(node => node.props.flexDirection === 'row' && (flat(node.children)[0] as Node | undefined)?.props?.minWidth !== undefined)
    .map(node => {
      const head = flat(node.children)[0] as Node
      const indented = all(head, 'Box').find(box => box.props.marginLeft !== undefined)
      return [indented?.props.marginLeft ?? 0, words(node)] as [number, string]
    })
}

const TARGETS = ['dev', 'test', 'prod']
const step = (id: string, name: string, heading: string) => TARGETS.map(target =>
  ({ key: `gate_steps.${id}.${target}`, type: 'bool' as const, label: `Gate step ${name} on ${target}`, group: 'Gate steps', step: name, heading }))
const SCHEMA = [
  { key: 'reply.length', type: 'enum' as const, label: 'Reply length', group: 'Session', options: ['short', 'long'] },
  ...TARGETS.map(target => ({ key: `gates_before_push.${target}`, type: 'bool' as const, label: `Gates ${target}`, group: 'Gates' })),
  ...TARGETS.map(target => ({ key: `coverage_before_push.${target}`, type: 'bool' as const, label: `Coverage ${target}`, group: 'Coverage' })),
  ...step('lint', 'lint', 'formatter / linter'), ...step('sast', 'SAST', 'SAST'),
]
const values = (over: Record<string, boolean | string> = {}) =>
  ({ 'reply.length': 'short', 'gates_before_push.dev': false, 'gates_before_push.test': true, 'gates_before_push.prod': true, ...over })
const none = () => undefined
/** The Session tab with the steps' accordion open; `system` the System tab with it open. */
const OPEN = { folded: true, toggle: none, steps: { folded: false, toggle: none } }
const SYSTEM = { ...OPEN, folded: false }
const data = (over: Record<string, boolean | string> = {}, saved: Record<string, boolean | string> = values()) =>
  ({ schema: SCHEMA, values: values(over), sources: {}, saved: { values: saved, sources: {} }, agents: [] })

test('the steps come from the schema, in order, with their targets, name and heading; other keys are not steps', () => {
  expect(gateSteps(SCHEMA)).toEqual([
    { id: 'lint', name: 'lint', heading: 'formatter / linter', targets: TARGETS, locked: false },
    { id: 'sast', name: 'SAST', heading: 'SAST', targets: TARGETS, locked: false }])
  expect(gateSteps([{ key: 'gate_steps.x.dev.extra' }, { key: 'gate_steps.' }, { key: 'push.dev' }])).toEqual([])
  expect(gateSteps([{ key: 'gate_steps.x.dev' }])[0]!.name).toBe('x')
})

test('a step runs unless it is unticked; only targets whose gate is on get a box', () => {
  expect([stepOn({}, 'k'), stepOn({ k: true }, 'k'), stepOn({ k: false }, 'k')]).toEqual([true, true, false])
  expect(gatedTargets(values(), TARGETS)).toEqual(['test', 'prod'])
  expect(gatedTargets({}, TARGETS)).toEqual([])
})

test('open, the steps sit right under Gates, one step in, with no label of their own, a box per target whose gate is on', () => {
  const drawn = lines(settingsBody(ui, data({ 'gate_steps.sast.prod': false }), '', [], none, OPEN))
  const at = drawn.findIndex(([, text]) => text.startsWith('Gates'))
  expect(drawn[at]![1].startsWith('Gates▾')).toBe(true)
  expect(drawn.slice(at + 1, at + 3)).toEqual([[STEP_INDENT, 'lint[test][prod]'], [STEP_INDENT, 'SAST[test]prod']])
  expect(drawn[at + 3]![1].startsWith('Coverage')).toBe(true)
  expect(drawn.some(([, text]) => text === 'steps')).toBe(false)
})

test('the accordion starts closed: an arrow beside Gates, no step rows, and the arrow opens it', () => {
  expect(isFolded({}, 'steps')).toBe(FOLDED_AT_START.steps)
  expect(FOLDED_AT_START.steps).toBe(true)
  let toggled = 0
  const body = settingsBody(ui, data(), '', [], none, { folded: true, toggle: none, steps: { folded: true, toggle: () => { toggled += 1 } } })
  const texts = lines(body).map(([, text]) => text)
  expect(texts.find(text => text.startsWith('Gates'))!.startsWith('Gates▸')).toBe(true)
  expect(texts.some(text => text.startsWith('lint') || text.startsWith('SAST'))).toBe(false)
  all(body, 'Button').find(one => one.props.key === 'fold-steps')!.props.onPress()
  expect(toggled).toBe(1)
  // A caller that keeps no fold state gets the closed accordion too.
  expect(lines(settingsBody(ui, data(), '', [], none)).some(([, text]) => text.startsWith('lint'))).toBe(false)
})

test('a step key never falls through to the rows for settings no row names', () => {
  // The fallback draws any unnamed setting at the bottom; the step keys would add a stray box per step and target.
  const texts = lines(settingsBody(ui, data(), '', [], none, OPEN)).map(([, text]) => text)
  expect(texts.filter(text => text.includes('Gate step'))).toEqual([])
  expect(texts.filter(text => text.startsWith('lint') || text.startsWith('SAST')).length).toBe(2)
})

test('with no gate on there is no arrow and no step row, even open; the System tab follows the saved gates', () => {
  const off = { 'gates_before_push.test': false, 'gates_before_push.prod': false }
  const body = settingsBody(ui, data(off), '', [], none, OPEN)
  expect(lines(body).some(([, text]) => text.startsWith('lint'))).toBe(false)
  expect(all(body, 'Button').some(one => one.props.key === 'fold-steps')).toBe(false)
  const system = settingsBody(ui, data(off, values({ 'gates_before_push.dev': true })), '', [], none, SYSTEM)
  expect(lines(system).map(([, text]) => text).filter(text => text.startsWith('lint'))).toEqual(['lint[dev][test][prod]'])
})

test('a press on the Session tab is kept for this session and saved as the default; on System, saved only', () => {
  const pressed: string[] = []
  const press = (key: string, value: string, scope = 'session') => pressed.push(`${scope} ${key}=${value}`)
  const body = settingsBody(ui, data({ 'gate_steps.lint.test': false }), '', [], press, OPEN)
  const button = all(body, 'Button').find(one => one.props.key === 'session/gate_steps.lint.test')!
  button.props.onPress()
  expect(pressed).toEqual(['session gate_steps.lint.test=yes', 'saved gate_steps.lint.test=yes'])
  pressed.length = 0
  pressStep(press, 'gate_steps.sast.dev', 'no', 'saved')
  expect(pressed).toEqual(['saved gate_steps.sast.dev=no'])
})

test('the head column is wide enough for an indented step name', () => {
  expect(stepsWidth(SCHEMA)).toBe(STEP_INDENT + 'lint'.length + 2)
  const long = [{ key: 'gate_steps.x.dev', step: 'a-very-long-name' }]
  expect(headWidth({ schema: long, values: {}, sources: {}, agents: [] } as never)).toBe(STEP_INDENT + 'a-very-long-name'.length + 2)
})

test('the step rows have hover cards: the heading from the gate, then what unticking does; Gates names the arrow', () => {
  const body = settingsBody(ui, data(), '', [], none, OPEN)
  const cards = all(body, 'Box').filter(node => node.props.display === 'none').map(words)
  expect([cards.includes(`formatter / linter: ${STEP_HELP}`), ROW_HELP.Gates!.includes('arrow')]).toEqual([true, true])
  expect(STEP_HELP.includes('waived') && STEP_HELP.includes('never as passed')).toBe(true)
})

test('the steps.enforce row is labelled Plan now; Steps is no row of its own', () => {
  expect([ROW_LABELS.includes('Plan'), ROW_LABELS.includes('Steps'), (ROW_HELP.Plan ?? '').length > 10]).toEqual([true, false, true])
})

test('a locked step (the secret scan, SAST) is drawn ticked whatever the value, a press changes nothing, its card says why', () => {
  const locked = [...SCHEMA, ...step('secrets', 'secrets', 'secret scan').map(spec => ({ ...spec, locked: true }))]
  const pressed: string[] = []
  const body = settingsBody(ui, { ...data({ 'gate_steps.secrets.test': false }), schema: locked }, '', [], (key: string) => pressed.push(key), OPEN)
  expect(lines(body).map(([, text]) => text).filter(text => text.startsWith('secrets'))).toEqual(['secrets[test][prod]'])
  for (const one of all(body, 'Button').filter(button => String(button.props.key).includes('gate_steps.secrets'))) one.props.onPress()
  expect(pressed).toEqual([])
  const cards = all(body, 'Box').filter(node => node.props.display === 'none').map(words)
  expect(cards.includes(`secret scan: ${LOCKED_STEP_HELP}`) && LOCKED_STEP_HELP.includes('#19')).toBe(true)
  expect(gateSteps(locked).map(one => one.locked)).toEqual([false, false, true])
})

test('the engine glue builds the fold object from the saved state: the tab and the accordion, each with its own toggle', () => {
  const toggles: string[] = []
  const toggle = (id: string) => () => { toggles.push(id) }
  const start = settingsFolds({}, toggle)
  expect([start.folded, start.steps!.folded]).toEqual([true, true])
  const opened = settingsFolds({ steps: false, claude: false }, toggle)
  expect([opened.folded, opened.steps!.folded]).toEqual([false, false])
  opened.toggle()
  opened.steps!.toggle()
  expect(toggles).toEqual(['claude', 'steps'])
})
