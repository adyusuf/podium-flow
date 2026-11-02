// The gate's steps under the Gates row of Settings (user decisions 02/11/2026): an accordion that an arrow beside Gates
// opens, folded at start, with no label of its own; one row per step of scripts/gate-core.sh one step in, each with a
// checkbox per target whose gate is on, the way Coverage has one per target. The steps come from the schema, which reads them from GATE_STEPS in gate-lib.sh: no step is named
// here (rule #2). Engine-free like boxes.ts, which it was split out of so no file passes 300 lines (rule #9).
import { INDENT, option } from './controls'
import { LOCKED_STEP_HELP, STEP_HELP } from './help'
import type { Ui } from './controls'

type Scope = 'session' | 'saved'
type Press = (key: string, value: string, scope?: Scope) => void
type Values = Record<string, boolean | string>
type Spec = { key: string; step?: string; heading?: string; locked?: boolean }

/** The prefix of the steps' keys (`gate_steps.<id>.<target>`). */
export const GATE_STEP_PREFIX = 'gate_steps.'
/** The accordion's fold: `folded` hides the step rows (folded at start); `toggle` opens or closes it. */
export type StepsFold = { folded: boolean; toggle: () => void }

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

/** How far in a step's label starts, in cells: one step in from Gates. */
export const STEP_INDENT = INDENT

/** The widest head a step row needs: its indent, its name and a gap. 0 with no steps. */
export const stepsWidth = (schema: Spec[]) => Math.max(0, ...gateSteps(schema).map(step => STEP_INDENT + step.name.length + 2))

/** Whether this layer has steps to show: some step, and some target whose gate is on. Only then is there an arrow. */
export function hasSteps(schema: Spec[], values: Values) {
  const steps = gateSteps(schema)
  return steps.length > 0 && gatedTargets(values, [...new Set(steps.flatMap(step => step.targets))]).length > 0
}

/** The accordion's arrow beside the Gates label: ▸ folded, ▾ open; nothing when no step would show. */
export function stepsArrow(ui: Ui, schema: Spec[], values: Values, fold: StepsFold) {
  if (!hasSteps(schema, values)) return null
  return ui.h(ui.Button, { key: 'fold-steps', plain: true, onPress: fold.toggle }, fold.folded ? '▸' : '▾')
}

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

/** One row per step; they show only while the accordion is open and a target's gate is on in the layer drawn. */
export function stepLines(ui: Ui, schema: Spec[], press: Press, fold: StepsFold): StepLine[] {
  const shown = (values: Values) => !fold.folded && hasSteps(schema, values)
  return gateSteps(schema).map((step): StepLine => ({
    id: `step-${step.id}`, label: step.name, indent: STEP_INDENT, help: `${step.heading}: ${step.locked ? LOCKED_STEP_HELP : STEP_HELP}`,
    names: step.targets,
    shown,
    draw: (scope, values) => gatedTargets(values, step.targets).map(target => {
      const key = `${GATE_STEP_PREFIX}${step.id}.${target}`
      // A locked step is drawn ticked and a press changes nothing: the settings would refuse it anyway.
      if (step.locked) return option(ui, `${scope}/${key}`, target, 'check', true, () => undefined)
      const on = stepOn(values, key)
      return option(ui, `${scope}/${key}`, target, 'check', on, () => pressStep(press, key, on ? 'no' : 'yes', scope))
    }),
  }))
}
