// The pane's data paths, split out of register.tsx so no file passes 300 lines (rule #9) and so they can be tested without
// the engine: no import from it. Each function takes the engine's `$` (typed in port.ts as only the calls it makes), so a
// test hands in a fake one; register.tsx keeps the hooks and the drawing.
import { outsideRepository, type Scope } from './boxes'
import { countOf, overrideNote, plannedStages, refSet, waivedLines, waivedRange } from './choose'
import { warnings } from './notices'
import {
  type Engine, type Layer, promotion, scriptPath, sessionId, settings, settingsError, settingsProblems, type SettingsData,
  type StageData, status,
} from './port'
import { parseStatus, statusDir, statusScript, statusStep, type StatusProbe } from './status'

async function readSettings($: Engine) {
  const run = (argv: string[]) => $.process.run(argv)
  const script = await scriptPath($)
  if (!script) {
    await $.state.set(settingsError, 'The podium plugin with /podium:config is not installed yet: /plugin update podium')
    return
  }
  const id = await sessionId($)
  const scope = id ? ['--session', id] : []
  const shown = await run(['python3', script, 'show', '--json', ...scope])
  const agents = await run(['python3', script, 'agents', '--json', '--all', ...scope])
  const schema = await run(['python3', script, 'schema'])
  // The "Claude settings" block: the shipped defaults and the user's own file, with no project or session layer (user decision 28/10/2026).
  const savedRead = await run(['python3', script, 'show', '--json', '--user'])
  if (shown.exitCode !== 0 || agents.exitCode !== 0 || schema.exitCode !== 0 || savedRead.exitCode !== 0) {
    await $.state.set(settingsError, (shown.stderr || agents.stderr || schema.stderr || savedRead.stderr || 'podium_config.py failed').slice(0, 300))
    return
  }
  try {
    const data = JSON.parse(shown.stdout) as Layer & { problems?: string[] }
    const saved = JSON.parse(savedRead.stdout) as Layer
    const next: SettingsData = {
      schema: JSON.parse(schema.stdout),
      values: data.values,
      sources: data.sources,
      saved: { values: saved.values, sources: saved.sources },
      agents: JSON.parse(agents.stdout),
    }
    // Every change since the last read (a press in the boxes, /podium:config, a hand edit) is a warning in the chat, with its rules.
    const { value: before = null } = await $.state.get(settings)
    await $.state.set(settings, next)
    for (const line of warnings(before, next)) $.ui.log(line)
    await $.state.set(settingsError, '')
    await $.state.set(settingsProblems, data.problems ?? [])
  } catch (error) {
    await $.state.set(settingsError, `Unreadable answer from podium_config.py: ${String(error).slice(0, 200)}`)
  }
}

async function readPromotion($: Engine) {
  const git = (args: string[]) => $.process.run(['git', ...args])
  // The engine says whether the folder is in a repository; any other git failure is only an error, never "outside".
  if (outsideRepository(await $.session.repo().catch(() => undefined))) {
    await $.state.set(promotion, { stages: [], error: 'Not inside a git repository', outside: true })
    return
  }
  const refs = await git(['for-each-ref', '--format=%(refname:short)', 'refs/heads', 'refs/remotes/origin'])
  if (refs.exitCode !== 0) {
    await $.state.set(promotion, { stages: [], error: `git failed: ${refs.stderr.trim().slice(0, 160)}` })
    return
  }
  const stages: StageData[] = []
  for (const stage of plannedStages(refSet(refs.stdout))) {
    const tip = await git(['rev-parse', '--short', `origin/${stage.branch}`])
    const ahead = stage.local ? await git(['rev-list', '--count', `origin/${stage.branch}..${stage.branch}`]) : null
    const range = waivedRange(stage)
    const log = range ? await git(['log', '--format=@@%h%n%B', range]) : null
    stages.push({
      branch: stage.branch,
      origin: tip.stdout.trim(),
      unpushed: ahead ? countOf(ahead.stdout) : 0,
      waived: log && log.exitCode === 0 ? waivedLines(log.stdout) : [],
    })
  }
  await $.state.set(promotion, { stages })
}

/** `session` writes this session's layer; `saved` writes the user's file, the defaults every new session starts from. */
async function setSetting($: Engine, key: string, value: string, scope: Scope, refreshSettings: (one: Engine) => Promise<void>) {
  const script = await scriptPath($)
  if (!script) {
    await $.ui.toast('The podium plugin is not installed yet: /plugin install podium@podium-marketplace')
    return
  }
  const id = scope === 'session' ? await sessionId($) : ''
  if (scope === 'session' && !id) {
    await $.ui.toast('Could not tell which session this is, so nothing was changed (the saved defaults stay as they are)')
    return
  }
  const done = await $.process.run(['python3', script, 'set', ...(id ? ['--session', id] : []), key, value])
  if (done.exitCode !== 0) await $.ui.toast(done.stderr.trim().slice(0, 200) || 'The change was refused')
  await refreshSettings($)
  const { value: now = null } = await $.state.get(settings)
  const layer = scope === 'saved' ? now?.saved : now
  if (done.exitCode === 0 && layer) {
    const note = overrideNote(key, value, layer.values[key], layer.sources[key])
    if (note) await $.ui.toast(note)
  }
}

/** This session's status file ('' when the engine will not say which session this is, or no folder is usable). */
async function statusPath($: Engine): Promise<string> {
  const id = await sessionId($)
  const dir = statusDir((await $.env.get('PODIUM_STATUS_DIR')) || (await $.env.get('ADYUSUF_STATUS_DIR')), await $.env.get('USERPROFILE'), await $.env.get('HOME'))
  return id && dir ? `${dir}/${id}.json` : ''
}

/** The file's modification time at the last read (status.ts's statusStep decides from it), and whether the box said it cannot read. */
type StatusMemo = { stamp: number; warned: boolean }

/** One refresh: look at the file, then read, clear or keep as statusStep says. A read error keeps the last table. */
async function readStatus($: Engine, memo: StatusMemo) {
  const path = await statusPath($)
  if (!path) return
  let probe: StatusProbe
  try {
    probe = (await $.fs.exists(path)) ? { kind: 'file', mtimeMs: (await $.fs.stat(path)).mtimeMs } : { kind: 'missing' }
  } catch {
    probe = { kind: 'error' }
  }
  let step = statusStep(memo.stamp, probe)
  if (step.action === 'read') {
    try {
      await $.state.set(status, parseStatus(await $.fs.read(path)))
    } catch {
      step = statusStep(step.stamp, { kind: 'error' })
    }
  } else if (step.action === 'clear') {
    await $.state.set(status, null)
  }
  memo.stamp = step.stamp
  if (step.stamp === -1 && !memo.warned) {
    memo.warned = true
    $.ui.log(`podium: the Status box cannot read ${path}; it keeps its last table and tries again`)
  }
}

/** The pane's queues and what they remember, one set per process: register.tsx makes it once, a test makes its own. */
export function createGlue() {
  const memo: StatusMemo = { stamp: -1, warned: false }
  const refreshSettings = ($: Engine) => readSettings($)
  const refreshPromotion = ($: Engine) => readPromotion($)

  // Refreshes run one after another (trigger, poll and turn end may overlap): an older read must not land after a newer one.
  // `again` forgets the stamp first, so the file is read anew (/podium:panels).
  let statusQueue: Promise<void> = Promise.resolve()
  function refreshStatus($: Engine, again = false): Promise<void> {
    if (again) memo.stamp = -1
    statusQueue = statusQueue.then(() => readStatus($, memo)).catch(() => undefined)
    return statusQueue
  }

  // Clicks run one after another: two settings changed quickly must not race each other's read-modify-write. A press
  // that fails (the script cannot be spawned) is said in a toast and the log, never dropped (F-030); the next one still runs.
  let queue: Promise<void> = Promise.resolve()
  function click($: Engine, key: string, value: string, scope: Scope): Promise<void> {
    queue = queue.then(() => setSetting($, key, value, scope, refreshSettings)).catch(error => {
      $.ui.log(`podium: a press in the Settings box failed: ${String(error).slice(0, 200)}`)
      $.ui.toast(`The change could not be made: ${String(error).slice(0, 160)}`)
    })
    return queue
  }

  // An interrupted turn fires no Stop hook, so the pane marks the Status box as waiting itself (qa, 02/11/2026).
  async function waitAfterInterrupt($: Engine) {
    const script = statusScript(await scriptPath($))
    await $.process.run(['python3', script, 'hook', 'stop'], { stdin: JSON.stringify({ session_id: await sessionId($) }) })
  }

  return { refreshSettings, refreshPromotion, refreshStatus, click, waitAfterInterrupt }
}
