import type { EngineInterface, Hook, Register } from 'claude-code'
import {
  agentsBody, FOLDED_AT_START, isFolded, nextFold, paneFor, promotionBody, section, settingsBody, settingsFolds,
  type FoldId, type Scope, type SectionId,
} from './boxes'
import { createGlue } from './glue'
import { operationWarnings } from './notices'
import { folded, promotion, safely, settings, settingsError, settingsProblems, status } from './port'
import { statusBody } from './status'

/** One pane, four bordered boxes in it (Status, Settings, Agents, Promotion), each folded by its header. */
const BOXES = 'podium-boxes'
const TITLE = 'podium'

/** How often the Status box looks at its file while nothing else wakes it (a background run writing its steps). */
const STATUS_POLL_MS = 2000

// The data paths (settings, promotion, status, presses) live in glue.ts, engine-free so they are tested with a fake `$`.
const glue = createGlue()
// The one poll of this process: a second session.start (a resume, a reload) replaces it instead of stacking another.
let statusPoll: { cancel: () => void } | undefined

/** Folds or unfolds one box of the pane, or switches the Settings tab; called from a press, never while drawing. */
async function flip($: EngineInterface, id: FoldId) {
  const { value: now = FOLDED_AT_START } = await $.state.get(folded)
  await $.state.set(folded, nextFold(now, id))
}

const onStart: Hook<'session.start'> = async ($, e, next) => {
  await $.command.register({ name: 'podium:panels', description: 'Open the podium status, settings, agents and promotion boxes', immediate: true })
  void $.ui.open({ id: BOXES, title: TITLE })
  await safely($, glue.refreshSettings($))
  await safely($, glue.refreshPromotion($))
  await glue.refreshStatus($)
  // Polling covers what changes while no tool runs (a background gate writing its steps); it reads only on a new mtime.
  statusPoll?.cancel()
  statusPoll = $.clock.every(STATUS_POLL_MS, () => void glue.refreshStatus($))
  return next(e)
}

const onPanels: Hook<'command.run'> = async $ => {
  await $.ui.open({ id: BOXES, title: TITLE })
  await safely($, glue.refreshSettings($))
  await safely($, glue.refreshPromotion($))
  await glue.refreshStatus($, true)
  return { text: 'podium boxes opened.' }
}

// The boxes follow the work: a turn may have merged, pushed or changed a setting through /podium:config.
const onTurnComplete: Hook<'turn.complete'> = async ($, e, next) => {
  if (e.isAborted && !e.agentId) await safely($, glue.waitAfterInterrupt($))
  await safely($, glue.refreshSettings($))
  await safely($, glue.refreshPromotion($))
  await glue.refreshStatus($)
  return next(e)
}

// The trigger: when a tool call returns (Claude's own status update is one), the Status box is current at once.
const onAnyTool: Hook<'tool.call'> = async ($, e, next) => {
  const result = await next(e)
  // `next(e)` resolves with the tool's own result (ToolCallResult), so this runs after the tool. Not awaited: the refresh
  // must never delay or fail the tool call it follows; refreshStatus never rejects.
  void glue.refreshStatus($)
  return result
}

// A merge, a push or a gate run in a shell command is a warning in the chat before it runs, with the rules it falls under.
const onShell: Hook<'tool.call'> = async ($, e, next) => {
  const command = 'command' in e ? String(e.command) : ''
  for (const line of operationWarnings(command)) $.ui.log(line)
  return next(e)
}

const onRender: Hook<'ui.render'> = async ($, e) => {
  const ui = { ...$.ui.resolve(e), h: (type: unknown, props: Record<string, unknown> | null, ...children: unknown[]) => h(type as never, props, ...children) }
  const { Box } = ui
  const { value: data = null } = await $.state.get(settings)
  const { value: problem = '' } = await $.state.get(settingsError)
  const { value: problems = [] } = await $.state.get(settingsProblems)
  const { value: stages = null } = await $.state.get(promotion)
  const { value: fold = FOLDED_AT_START } = await $.state.get(folded)
  const { value: now = null } = await $.state.get(status)
  const press = (key: string, value: string, scope: Scope = 'session') => void glue.click($, key, value, scope)
  const toggle = (id: FoldId) => () => void flip($, id)
  const shut = (id: SectionId) => isFolded(fold, id)
  const claude = settingsFolds(fold, toggle)
  const pane = paneFor(stages)
  return (
    <Box flexDirection="column">
      {section(ui, 'status', 'Status', shut('status'), toggle('status'), statusBody(ui, now, { folded: id => isFolded(fold, id), toggle }))}
      {section(ui, 'settings', 'Settings', shut('settings'), toggle('settings'),
        settingsBody(ui, data, problem, problems, press, claude, pane.codeWork))}
      {pane.sections.includes('agents') ? section(ui, 'agents', 'Agents', shut('agents'), toggle('agents'),
        agentsBody(ui, data, press)) : null}
      {pane.sections.includes('promotion') ? section(ui, 'promotion', 'Promotion', shut('promotion'), toggle('promotion'),
        promotionBody(ui, stages)) : null}
    </Box>
  )
}

export const register: Register = on => {
  on('session.start', onStart)
  on('command.run', { command: 'podium:panels' }, onPanels)
  on('turn.complete', onTurnComplete)
  on('tool.call', { tool: 'Bash' }, onShell)
  on('tool.call', { tool: 'PowerShell' }, onShell)
  on('tool.call', onAnyTool)
  on('ui.render', { component: 'Pane', requestId: BOXES }, onRender)
}
