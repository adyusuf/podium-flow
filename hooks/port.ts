// What the pane's data paths (glue.ts) need of the engine, typed as only the calls they make, so a test hands in a fake
// `$` instead of the engine's: the state slots, the installed plugin's script, the session id and the queue the
// refreshes run in. No import from the engine; register.tsx hands its own `$` in.
import { DISCOVER_PY, IS_FILE_PY, parseDiscovery, scriptDir } from './choose'
import type { StatusData } from './status'

export type Ran = { exitCode: number; stdout: string; stderr: string }
export type Layer = { values: Record<string, boolean | string>; sources: Record<string, string> }
/** What the Settings and Agents boxes read; ../types declares the same shapes for the engine. */
export type SettingsData = Layer & { schema: Array<{ key: string; label: string }>; saved?: Layer; agents: unknown[] }
export type StageData = { branch: string; origin: string; unpushed: number; waived: string[] }
export type PromotionData = { stages: StageData[]; error?: string; outside?: boolean }

type Slot<K extends string> = { readonly plugin: 'podium'; readonly key: K }

/**
 * The engine calls the data paths make, nothing more. Method syntax and one signature per state slot, so the engine's
 * own generic `$` fits it (checked against the engine's declarations, 14/11/2026).
 */
export type Engine = {
  process: { run(argv: readonly string[], init?: { stdin?: string }): Promise<Ran> }
  state: {
    get(ref: Slot<'settings'>): Promise<{ value?: SettingsData | null }>
    set(ref: Slot<'settings'>, value: SettingsData): Promise<unknown>
    set(ref: Slot<'settingsError'>, value: string): Promise<unknown>
    set(ref: Slot<'settingsProblems'>, value: string[]): Promise<unknown>
    set(ref: Slot<'promotion'>, value: PromotionData): Promise<unknown>
    set(ref: Slot<'status'>, value: StatusData | null): Promise<unknown>
  }
  ui: { toast(text: string): unknown; log(text: string): void }
  session: { id(): Promise<string>; repo(): Promise<unknown> }
  env: { get(name: string): Promise<string | undefined> }
  fs: { exists(path: string): Promise<boolean>; stat(path: string): Promise<{ mtimeMs: number }>; read(path: string): Promise<string> }
}

// The pane's values live in `$.state`, declared in ../types; a value never written reads as undefined, so each read names its initial one.
export const settings = { plugin: 'podium', key: 'settings' } as const
export const settingsError = { plugin: 'podium', key: 'settingsError' } as const
export const settingsProblems = { plugin: 'podium', key: 'settingsProblems' } as const
export const promotion = { plugin: 'podium', key: 'promotion' } as const
export const folded = { plugin: 'podium', key: 'folded' } as const
export const status = { plugin: 'podium', key: 'status' } as const

const PLUGIN = 'podium'
const MARKETPLACE = 'podium-marketplace'
const PLUGIN_ID = `${PLUGIN}@${MARKETPLACE}`

/** The configuration script of the INSTALLED podium plugin ('' when it has none yet); the choice is choose.ts's scriptDir. */
export async function scriptPath($: Engine): Promise<string> {
  const found = await $.process.run(['python3', '-c', DISCOVER_PY, MARKETPLACE, PLUGIN])
  const { record, listing } = parseDiscovery(found.stdout)
  const dir = scriptDir(record, PLUGIN_ID, listing)
  if (!dir) return ''
  const script = `${dir}/scripts/podium_config.py`
  const has = await $.process.run(['python3', '-c', IS_FILE_PY, script])
  return has.exitCode === 0 ? script : ''
}

/** This session's id ('' when the engine will not say): the boxes change THIS session's layer only, never the saved defaults. */
export async function sessionId($: Engine): Promise<string> {
  try {
    return (await $.session.id()) || ''
  } catch {
    return ''
  }
}

/** A failing read must never stop the session from starting; the Settings box says what failed instead of waiting forever. */
export async function safely($: Engine, work: Promise<void>) {
  try {
    await work
  } catch (error) {
    await $.state.set(settingsError, `Could not read: ${String(error).slice(0, 200)}`)
  }
}

/**
 * One after another: a job starts when every job queued before it has ended. A failure reaches the job's own caller and
 * never stops the jobs queued behind it (only the queue's tail lets it go; the caller's promise still rejects with it).
 */
export function serial() {
  let tail: Promise<void> = Promise.resolve()
  return <T>(job: () => Promise<T>): Promise<T> => {
    const run = tail.then(job)
    tail = run.then(() => undefined, () => undefined)
    return run
  }
}
