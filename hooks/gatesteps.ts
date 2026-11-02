// The gate's steps under the Gates row of Settings (user decision 02/11/2026): a `steps` label one step in, then one row
// per step of scripts/gate-core.sh two steps in, each with a checkbox per target whose gate is on, the way Coverage has
// one per target. The steps come from the schema, which reads them from GATE_STEPS in gate-lib.sh: no step is named
// here (rule #2). Engine-free like boxes.ts, which it was split out of so no file passes 300 lines (rule #9).
import { INDENT, option } from './controls'
import { LOCKED_STEP_HELP, STEP_HELP, STEPS_HELP } from './help'
import type { Ui } from './controls'

type Scope = 'session' | 'saved'
type Press = (key: string, value: string, scope?: Scope) => void
type Values = Record<string, boolean | string>
type Spec = { key: string; step?: string; heading?: string; locked?: boolean }

/** The label above the step rows, and the prefix of their keys (`gate_steps.<id>.<target>`). */
export const STEPS_LABEL = 'steps'
export const GATE_STEP_PREFIX = 'gate_steps.'

/** `locked`: a step nobody can untick (the secret scan and SAST, rule #19; user decision 02/11/2026). */
export type GateStep = { id: string; name: string; heading: string; targets: string[]; locked: boolean }

/** The gate's steps in schema order, each with the targets it has a setting for. */
export function gateSteps(schema: Spec[]): GateStep[] {
  const steps: GateStep[] = []
  for (const spec of schema) {
    if (!spec.key.startsWith(GATE_STEP_PREFIX)) continue
    const [id, target, ...rest] = spec.key.slice(GATE_STEP_PREFIX.length).split('.')
    if (!id || !target || rest.length > 0) continue
    let step = steps.find(one => one.id === id)
    if (!step) {
      step = { id, name: spec.step ?? id, heading: spec.heading ?? id, targets: [], locked: false }
      steps.push(step)
    }
    step.targets.push(target)
    if (spec.locked) step.locked = true
  }
  return steps
}

/** The targets whose gate is on in this layer: only they get a step's checkbox, and with none the block is hidden. */
export const gatedTargets = (values: Values, targets: string[]) => targets.filter(target => values[`gates_before_push.${target}`] === true)

/** A step runs unless it is unticked: a missing value is the default, on. */
export const stepOn = (values: Values, key: string) => values[key] !== false

/** How far in a row's label starts, in cells: `steps` one step in, a step two. */
export const STEPS_INDENT = INDENT
export const STEP_INDENT = 2 * INDENT

/** The widest head a step row needs: its indent, its name and a gap. 0 with no steps. */
export const stepsWidth = (schema: Spec[]) =>
  Math.max(0, ...gateSteps(schema).map(step => STEP_INDENT + step.name.length + 2), STEPS_INDENT + STEPS_LABEL.length + 2)

/**
 * A press on a step. On the Session tab it is written to this session and to the saved defaults as well, so the next
 * session starts with the last selection ticked (user decision 02/11/2026: "the last selection comes back"); on the
 * System tab it is the saved defaults alone.
 */
export function pressStep(press: Press, key: string, value: string, scope: Scope) {
  press(key, value, scope)
  if (scope === 'session') press(key, value, 'saved')
}

/** One row of the steps block, in the shape boxes.ts draws its settings rows. */
export type StepLine = {
  id: string; label: string; indent: number; help: string; names: string[]
  shown: (values: Values) => boolean
  draw: (scope: Scope, values: Values) => unknown[]
}

/** The `steps` label row and one row per step; each shows only while a target's gate is on in the layer drawn. */
export function stepLines(ui: Ui, schema: Spec[], press: Press): StepLine[] {
  const steps = gateSteps(schema)
  if (steps.length === 0) return []
  const all = [...new Set(steps.flatMap(step => step.targets))]
  const anyGate = (values: Values) => gatedTargets(values, all).length > 0
  const head: StepLine = { id: 'steps', label: STEPS_LABEL, indent: STEPS_INDENT, help: STEPS_HELP, names: [], shown: anyGate, draw: () => [] }
  return [head, ...steps.map((step): StepLine => ({
    id: `step-${step.id}`, label: step.name, indent: STEP_INDENT, help: `${step.heading}: ${step.locked ? LOCKED_STEP_HELP : STEP_HELP}`,
    names: step.targets,
    shown: anyGate,
    draw: (scope, values) => gatedTargets(values, step.targets).map(target => {
      const key = `${GATE_STEP_PREFIX}${step.id}.${target}`
      // A locked step is drawn ticked and a press changes nothing: the settings would refuse it anyway.
      if (step.locked) return option(ui, `${scope}/${key}`, target, 'check', true, () => undefined)
      const on = stepOn(values, key)
      return option(ui, `${scope}/${key}`, target, 'check', on, () => pressStep(press, key, on ? 'no' : 'yes', scope))
    }),
  }))]
}
