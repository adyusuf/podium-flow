// What the boxes of the podium pane show, kept apart from the engine so it can be tested without one: no import from
// 'claude-code', no JSX. The element factory `h` and the elements themselves (Box, Text, Button) are handed in as
// `ui`: each surface has its own elements, and a test hands in a recording factory instead of the engine's. A choice among
// several values is a row of options, not a dropdown (user decision 24/10/2026); every setting sits on one line, the label
// first and its pressable parts after it (user decision 28/10/2026). User decisions of 01/11/2026: the labels are short and
// bold, with no trailing colon, in a column of one width so every row's options start at the same place; what is chosen or on
// is at full strength and the rest dimmed; where the surface draws `Svg` (desktop) each option has a radio or checkbox icon,
// where it does not (terminal) the chosen one is drawn `[in brackets]` (underline was tried first: the desktop draws a Button
// as a native button and drops a Text's underline inside it); a box's body and a block's lines start one step in.
import { enabledFor, settingGroups } from './choose'
import { explained, helpCard, INDENT, INFO_CELLS, label, line, option, WARN } from './controls'
import { GATE_STEP_PREFIX, stepLines, stepsArrow, stepsWidth, type StepsFold } from './gatesteps'
import { COLUMN_HELP, ROW_HELP, SECTION_HELP, STAGE_HELP, STAGE_TAIL } from './help'
import { NO_CODE_ROWS, ROWS, type Item } from './rows'
import type { Ui } from './controls'

export type { Factory, Ui } from './controls'
export { NO_CODE_ROWS, ROW_LABELS, ROWS } from './rows'

/** `session`: this session only; `saved`: the saved defaults every new session starts from (the user's file). */
export type Scope = 'session' | 'saved'
export type Press = (key: string, value: string, scope?: Scope) => void

type Spec = {
  key: string; type: 'bool' | 'enum'; label: string; group: string; options?: string[]; legacy?: string[]; step?: string; heading?: string; locked?: boolean
}
type AgentRow = {
  role: string; defined: string; runs_on: string; default_model?: string; active: boolean; in_mode: boolean; enabled: string; model: string
  description?: string
}
type Layer = { values: Record<string, boolean | string>; sources: Record<string, string> }
type SettingsData = Layer & { schema: Spec[]; saved?: Layer; agents: AgentRow[] }
type Stage = { branch: string; origin: string; unpushed: number; waived: string[] }
type PromotionData = { stages: Stage[]; error?: string; outside?: boolean }

export const SECTIONS = ['status', 'settings', 'agents', 'promotion'] as const
export type SectionId = (typeof SECTIONS)[number]

/**
 * What the pane shows. Outside a git repository the session is taken as no-code work: only Status and Settings, and
 * Settings only the rows of NO_CODE_ROWS (user decisions 01/11/2026 and 09/11/2026; standards/13 §8a). Until the folder is read, and inside a repository,
 * everything shows; a git failure that is not "outside" leaves `outside` unset, so it hides nothing.
 */
export function paneFor(promotion: PromotionData | null): { sections: SectionId[]; codeWork: boolean } {
  const outside = promotion?.outside === true
  return { sections: outside ? ['status', 'settings'] : [...SECTIONS], codeWork: !outside }
}

/** Whether the session's folder is outside every git repository: the engine's `session.repo()` answers null. */
export const outsideRepository = (repo: unknown) => repo === null

/**
 * What starts folded, so the pane opens as a short card and not as one long list: two boxes, `claude`, which keeps
 * the Settings tab (folded = Session, the tab at start; the saved defaults are under System, opened when wanted), and
 * `steps`, the gate's steps under Gates (user decision 02/11/2026: an accordion, closed at start).
 */
export const FOLDED_AT_START: Record<string, boolean> = { agents: true, promotion: true, claude: true, steps: true }
/** What can fold: a box, `claude` (the Settings tab), `steps`, or a Status agent (`agent:<name>` and its `:todo`, `:done`). */
export type FoldId = SectionId | 'claude' | 'steps' | `agent:${string}`

/** Whether `id` is folded; a state saved before `id` could fold falls back to how it starts. */
export const isFolded = (fold: Record<string, boolean>, id: FoldId) => fold[id] ?? FOLDED_AT_START[id] ?? id.endsWith(':done')
/** The fold state after a press on `id`'s header: what it reads as now, turned over. */
export const nextFold = (fold: Record<string, boolean>, id: FoldId) => ({ ...fold, [id]: !isFolded(fold, id) })
/** The Settings tab: `folded` (the fold id `claude`, folded at start) means the Session tab; `toggle` switches tabs. It
 * also carries the gate steps' accordion (`steps`), so the engine glue hands the box one fold object. */
export type ColumnFold = { folded: boolean; toggle: () => void; steps?: StepsFold }
/** That fold object, from the pane's fold state and its toggles. */
export const settingsFolds = (fold: Record<string, boolean>, toggle: (id: FoldId) => () => void): ColumnFold =>
  ({ folded: isFolded(fold, 'claude'), toggle: toggle('claude'), steps: { folded: isFolded(fold, 'steps'), toggle: toggle('steps') } })

/** The radio group of an agent's model. */
const AGENT_MODELS = ['opus', 'sonnet', 'haiku', 'fable']
/** The names the Agents box shows; the role (agent file, settings key) keeps its own name. */
const ROLE_NAMES: Record<string, string> = {
  'product-manager': 'product', 'test-writer': 'tester', 'doc-writer': 'doc', 'coverage-auditor': 'coverage', 'e2e-writer': 'e2e',
}


/** The width of the label column of a settings block, in cells: the longest label and a gap. */
const LABEL_WIDTH = Math.max(...ROWS.map(row => row.label.length)) + 2

/** The name an Agents row shows: the short name and a star for an opus role (Model* replaces exactly those roles). */
const agentName = (agent: AgentRow) => `${ROLE_NAMES[agent.role] ?? agent.role}${agent.defined === 'opus' ? '*' : ''}`

/** Whether a role was added to the mode or taken out of it; drawn at the end of its row, so it never widens the names. */
function agentMark(agent: AgentRow, mode: string) {
  if (!agent.in_mode && agent.active) return '(added)'
  return agent.in_mode && !agent.active && mode !== 'A' ? '(off)' : ''
}

/**
 * The head column of Settings and Agents, one width for both, so their options start at the same place (user decision
 * 01/11/2026): the longest label, or the longest name of a role that is on (its checkbox and a gap counted). A role
 * that is off has no radios after it, so its name does not widen the column.
 */
export function headWidth(data: SettingsData) {
  // Every head carries its (i) after it (user decision 09/11/2026), so the column is that much wider.
  return INFO_CELLS + Math.max(LABEL_WIDTH, stepsWidth(data.schema), ...data.agents.filter(agent => agent.active).map(agent => agentName(agent).length + 3))
}

/** The options of one setting, the chosen one marked. */
function choices(ui: Ui, scope: Scope, key: string, options: Item[], value: string, press: Press) {
  return options.map(one =>
    option(ui, `${scope}/${key}=${one.key}`, one.name, 'radio', one.key === value, () => press(key, one.key, scope)))
}

/** The yes/no settings of one line, each marked while it is on; pressing asks for the opposite. */
function checks(ui: Ui, scope: Scope, items: Item[], values: Layer['values'], press: Press) {
  return items.map(item => {
    const on = values[item.key] === true
    return option(ui, `${scope}/${item.key}`, item.name, 'check', on, () => press(item.key, on ? 'no' : 'yes', scope))
  })
}

/**
 * One settings row: its label, the names it draws (to size the column) and how it draws its options for one layer. A gate
 * step row also has its own hover id, an indent, its card text and whether the layer shows it (gatesteps.ts).
 */
type SettingLine = {
  label: string; names: string[]; draw: (scope: Scope, layer: Layer) => unknown[]
  id?: string; indent?: number; help?: string; shown?: (layer: Layer) => boolean; after?: (layer: Layer) => unknown
}

/** The rows of the settings table, in order. */
function settingLines(ui: Ui, schema: Spec[], press: Press, steps: StepsFold): SettingLine[] {
  const { shown } = settingGroups(schema)
  const has = new Set(shown.map(spec => spec.key))
  const covered = new Set<string>()
  const lines: SettingLine[] = []
  // A value a file written before may hold (`legacy`, never offered) is drawn as one more option, chosen, while the
  // layer holds it, so the row never shows no value (qa 09/11/2026: a stored budget of 100).
  const radios = (text: string, key: string, options: Item[], legacy: string[] = []): SettingLine => ({
    label: text, names: options.map(one => one.name),
    draw: (scope, layer) => {
      const value = String(layer.values[key])
      const held = legacy.includes(value) && !options.some(one => one.key === value) ? [{ key: value, name: value }] : []
      // Pressing the held value changes nothing: `set` refuses a legacy value, so it would only raise an error.
      const quiet: Press = (pressed, wanted, at) => { if (!held.some(one => one.key === wanted)) press(pressed, wanted, at) }
      return choices(ui, scope, key, [...options, ...held], value, quiet)
    },
  })
  for (const row of ROWS) {
    if ('items' in row) {
      const items = row.items.filter(item => has.has(item.key))
      items.forEach(item => covered.add(item.key))
      // The gate's steps sit right under Gates, behind an arrow beside its label (user decisions 02/11/2026).
      const after = row.label === 'Gates' ? (layer: Layer) => stepsArrow(ui, shown, layer.values, steps) : undefined
      if (items.length > 0) {
        lines.push({ label: row.label, names: items.map(item => item.name), draw: (scope, layer) => checks(ui, scope, items, layer.values, press), after })
      }
      if (row.label === 'Gates') {
        lines.push(...stepLines(ui, shown, press, steps).map((one): SettingLine =>
          ({ ...one, draw: (scope, layer) => one.draw(scope, layer.values), shown: layer => one.shown(layer.values) })))
      }
      continue
    }
    const spec = shown.find(one => one.key === row.key)
    if (!spec) continue
    covered.add(row.key)
    lines.push(radios(row.label, row.key, (spec.options ?? []).map(option => ({ key: option, name: row.names?.[option] ?? option })), spec.legacy))
  }
  // A setting no row names (a newer plugin than this pane) must not vanish from view.
  for (const spec of shown.filter(one => !covered.has(one.key) && !one.key.startsWith(GATE_STEP_PREFIX))) {
    const items = [{ key: spec.key, name: spec.label }]
    lines.push(spec.type === 'bool'
      ? { label: '', names: [spec.label], draw: (scope, layer) => checks(ui, scope, items, layer.values, press) }
      : radios(spec.label, spec.key, (spec.options ?? []).map(option => ({ key: option, name: option }))))
  }
  return lines
}

/**
 * One bordered box with a header that folds it. The header is the arrow and the title alone, nothing beside it (user
 * decision 01/11/2026: a summary there made the pane cluttered). The title is a bold Text and only the arrow is pressable:
 * inside a Button the desktop drops the bold.
 */
export function section(ui: Ui, id: SectionId, title: string, folded: boolean, toggle: () => void, body: unknown) {
  const { h } = ui
  return h(
    ui.Box,
    { flexDirection: 'column', borderStyle: 'round', paddingX: 1, marginBottom: 1 },
    h(ui.Box, { flexDirection: 'row', columnGap: 1 },
      h(ui.Button, { key: `fold-${id}`, plain: true, onPress: toggle }, folded ? '▸' : '▾'),
      explained(ui, `section-${id}`, h(ui.Text, { bold: true }, title), SECTION_HELP[id])),
    helpCard(ui, `section-${id}`, SECTION_HELP[id]),
    folded ? null : h(ui.Box, { flexDirection: 'column', marginLeft: INDENT }, body),
  )
}

/**
 * The settings under two tabs (user decision 02/11/2026): Session (this session's options; a press changes this session
 * only) and System (the saved defaults in `~/.claude/podium.json`, which new sessions start from). One tab shows at a
 * time, the chosen one at full strength (in brackets in the terminal); the choice is kept as the fold id `claude`, so
 * a saved state from the System column it replaces still applies.
 */
function table(ui: Ui, data: SettingsData, press: Press, tabs: ColumnFold, codeWork: boolean) {
  const { h } = ui
  const head = headWidth(data)
  const system = data.saved !== undefined && !tabs.folded
  const [scope, layer]: [Scope, Layer] = system && data.saved ? ['saved', data.saved] : ['session', data]
  const lines = settingLines(ui, data.schema, press, tabs.steps ?? { folded: true, toggle: () => undefined })
    .filter(one => (codeWork || NO_CODE_ROWS.includes(one.label)) && (one.shown?.(layer) ?? true))
  // A tab is drawn as every other choice of the pane: a radio icon on the desktop, brackets in the terminal.
  const tab = (name: 'Session' | 'System', chosen: boolean) => explained(ui, `column-${name}`,
    option(ui, `tab-${name}`, name, 'radio', chosen, () => { if (!chosen) tabs.toggle() }), COLUMN_HELP[name])
  // Each card is a hidden row right after its label's line.
  return h(ui.Box, { flexDirection: 'column' },
    line(ui, null, [h(ui.Box, { flexDirection: 'row', columnGap: 1 }, tab('Session', !system), data.saved ? tab('System', system) : null)], head),
    helpCard(ui, 'column-Session', COLUMN_HELP.Session),
    data.saved ? helpCard(ui, 'column-System', COLUMN_HELP.System) : null,
    lines.flatMap(one => {
      const card = one.help ?? ROW_HELP[one.label]
      return [
        line(ui, h(ui.Box, { flexDirection: 'row', columnGap: 1 },
          explained(ui, `row-${one.id ?? one.label}`, label(ui, one.label, one.indent), one.label === '' ? undefined : card),
          one.after?.(layer) ?? null), [one.draw(scope, layer)], head),
        helpCard(ui, `row-${one.id ?? one.label}`, card)]
    }))
}

/** The Session tab, for a caller that keeps no tab state. */
const OPEN: ColumnFold = { folded: true, toggle: () => undefined }

export function settingsBody(ui: Ui, data: SettingsData | null, problem: string, problems: string[], press: Press, claude = OPEN,
  codeWork = true) {
  const { h } = ui
  if (!data) return h(ui.Text, { dimColor: true }, problem || 'Reading the configuration…')
  return h(
    ui.Box,
    { flexDirection: 'column' },
    problem !== '' ? h(ui.Text, { color: 'red' }, problem) : null,
    problems.map(line => h(ui.Text, { color: WARN }, `! ${line}`)),
    codeWork ? null : h(ui.Text, { dimColor: true }, 'No repository here: only the rows for work without code show. Change the rest with /podium:config.'),
    table(ui, data, press, claude, codeWork),
  )
}

export function agentsBody(ui: Ui, data: SettingsData | null, press: Press) {
  const { h } = ui
  if (!data) return h(ui.Text, { dimColor: true }, 'Reading the configuration…')
  const mode = String(data.values.mode)
  const width = headWidth(data)
  // User decisions 01/11/2026: a row is the role's checkbox with its name (pressing the name toggles it, as in Settings),
  // then the model as one radio group; the `default` checkbox that sat between them is gone. The radio of the model the
  // role runs on is chosen; choosing the model `default` gives writes `default`, any other pins that model.
  const role = (agent: AgentRow) => option(ui, `on-${agent.role}`, agentName(agent), 'check', agent.active, () => {
    if (mode === 'A') return
    press(`agents.${agent.role}.enabled`, enabledFor(!agent.active, agent.in_mode))
  })
  const key = (agent: AgentRow) => `agents.${agent.role}.model`
  // The model `default` gives; from an older script without `default_model`, known only while the role is on `default`.
  const givenByDefault = (agent: AgentRow) => agent.default_model ?? (agent.model === 'default' ? agent.runs_on : undefined)
  const mark = (agent: AgentRow) => (agentMark(agent, mode) === '' ? null : h(ui.Text, { dimColor: true }, agentMark(agent, mode)))
  const models = (agent: AgentRow) => AGENT_MODELS.map(model => option(ui, `${key(agent)}=${model}`, model, 'radio', model === agent.runs_on,
    () => press(key(agent), model === givenByDefault(agent) ? 'default' : model)))
  return h(
    ui.Box,
    { flexDirection: 'column' },
    // The header says nothing beside its title, so mode A, where no press takes effect, says so here.
    mode === 'A' ? h(ui.Text, { dimColor: true }, 'mode A runs no agents') : null,
    // A role's card is its agent file's description, a hidden row right after its line.
    data.agents.flatMap(agent => [
      line(ui, explained(ui, `agent-${agent.role}`, role(agent), agent.description), [[...(agent.active ? models(agent) : []), mark(agent)]], width),
      helpCard(ui, `agent-${agent.role}`, agent.description)]),
  )
}

/** A stage line's card: the branch's own words, then what the line shows. */
const stageCard = (branch: string) => `${STAGE_HELP[branch] ?? `${branch}:`} ${STAGE_TAIL}`

export function promotionBody(ui: Ui, data: PromotionData | null) {
  const { h } = ui
  if (!data) return h(ui.Text, { dimColor: true }, 'Reading the branches…')
  if (data.error) return h(ui.Text, { dimColor: true }, data.error)
  return h(
    ui.Box,
    { flexDirection: 'column' },
    data.stages.map(stage =>
      h(ui.Box, { flexDirection: 'column', marginBottom: 1 },
        explained(ui, `stage-${stage.branch}`, h(ui.Text, { bold: true }, `${stage.branch.padEnd(5)} origin ${stage.origin}${stage.unpushed > 0 ? `  ${stage.unpushed} not pushed` : '  pushed'}`), stageCard(stage.branch)),
        helpCard(ui, `stage-${stage.branch}`, stageCard(stage.branch)),
        h(ui.Box, { flexDirection: 'column', marginLeft: INDENT },
          stage.waived.length === 0
            ? h(ui.Text, { dimColor: true }, 'no waived gate on the way in')
            : stage.waived.map(line => h(ui.Text, { color: WARN }, `waived ${line}`))))),
    data.stages.length === 0 ? h(ui.Text, { dimColor: true }, 'No dev, test or prod branch here.') : null,
  )
}
