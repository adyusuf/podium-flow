// A fake engine `$` for the data-path tests (glue.test.ts, paths.test.ts): it records what the pane runs, toasts, logs
// and stores, and answers like the installed plugin's podium_config.py. Named `.test.ts` so the coverage step counts it
// as test code, not as logic of the mod; it holds no test of its own.
import type { Engine, Ran } from './port'

export const SCRIPT = '/plugin/scripts/podium_config.py'
export const STATUS_SCRIPT = '/plugin/scripts/podium_status.py'
const RECORD = JSON.stringify({ plugins: { 'podium@podium-marketplace': [{ installPath: '/plugin' }] } })

export const ok = (stdout = ''): Ran => ({ exitCode: 0, stdout, stderr: '' })
export const fail = (stderr: string, exitCode = 1): Ran => ({ exitCode, stdout: '', stderr })
export const later = () => new Promise<void>(resolve => setTimeout(resolve, 5))

type Values = Record<string, boolean | string>
/** The configuration the fake script keeps: the saved defaults, this session's layer, and a layer above both. */
export type Layers = { saved: Values; session: Values; project: Values }
const SCHEMA = [{ key: 'mode', label: 'Mode' }, { key: 'push.prod', label: 'Push prod' }, { key: 'gate_steps.sast.dev', label: 'SAST dev' }]
const stored = (value: string) => (value === 'yes' ? true : value === 'no' ? false : value)

/** What `python3 podium_config.py …` answers for the layers; `set` writes the session or the saved layer. */
export function configScript(layers: Layers) {
  const layer = (...names: Array<keyof Layers>) => {
    const values: Values = {}
    const sources: Record<string, string> = {}
    for (const name of names) for (const [key, value] of Object.entries(layers[name])) { values[key] = value; sources[key] = name === 'saved' ? 'user' : name }
    return JSON.stringify({ values, sources })
  }
  return (argv: readonly string[]): Ran => {
    const [, , command, ...rest] = argv
    if (command === 'show') return ok(rest.includes('--user') ? layer('saved') : layer('saved', 'session', 'project'))
    if (command === 'agents') return ok('[]')
    if (command === 'schema') return ok(JSON.stringify(SCHEMA))
    if (command === 'set') {
      const session = rest[0] === '--session'
      const [key, value] = session ? rest.slice(2) : rest
      layers[session ? 'session' : 'saved'][key] = stored(value)
      return ok()
    }
    return fail(`unknown command ${command}`)
  }
}

export type Fake = Engine & {
  runs: string[][]; stdins: string[]; toasts: string[]; logs: string[]; store: Map<string, unknown>
  /** What `$.process.run` answers past the plugin lookup (which finds SCRIPT unless `found` is false). */
  answer: (argv: readonly string[]) => Ran | Promise<Ran>
  found: boolean; id: string | Error; repo: unknown
  files: Record<string, { mtimeMs: number; text: string } | Error>
}

/** A fresh fake: the plugin is found, the session is `s1`, the folder is a repository, no status file. */
export function fake(answer: Fake['answer'] = () => fail('no answer set')): Fake {
  const one: Fake = {
    runs: [], stdins: [], toasts: [], logs: [], store: new Map(), answer, found: true, id: 's1', repo: {}, files: {},
    process: {
      run: async (argv, init) => {
        one.runs.push([...argv])
        if (init?.stdin !== undefined) one.stdins.push(init.stdin)
        if (argv[1] === '-c' && argv.length === 5) return ok(JSON.stringify({ record: one.found ? RECORD : '', cache: [] }))
        if (argv[1] === '-c') return argv[3] === SCRIPT && one.found ? ok() : fail('')
        return one.answer(argv)
      },
    },
    state: {
      get: async (ref: { key: string }) => ({ value: one.store.get(ref.key) as never }),
      set: async (ref: { key: string }, value: unknown) => { one.store.set(ref.key, value) },
    } as Engine['state'],
    ui: { toast: text => { one.toasts.push(text) }, log: text => { one.logs.push(text) } },
    session: {
      id: async () => { if (one.id instanceof Error) throw one.id; return one.id },
      repo: async () => { if (one.repo instanceof Error) throw one.repo; return one.repo },
    },
    env: { get: async name => (name === 'PODIUM_STATUS_DIR' ? '/status' : undefined) },
    fs: {
      exists: async path => path in one.files,
      stat: async path => { const file = one.files[path]; if (file instanceof Error) throw file; return { mtimeMs: file.mtimeMs } },
      read: async path => { const file = one.files[path]; if (file instanceof Error) throw file; return file.text },
    },
  }
  return one
}

/** The commands the pane ran past the plugin lookup, each as its words after `python3 <script>` or `git`. */
export const commands = (one: Fake) =>
  one.runs.filter(argv => argv[1] !== '-c').map(argv => (argv[0] === 'git' ? argv.slice(1) : argv.slice(2)).join(' '))
