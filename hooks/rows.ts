// The rows of the Settings box: their labels and the settings each one draws, in order. Split out of boxes.ts so no file
// passes 300 lines (rule #9); boxes.ts re-exports every name here.

const TARGETS = ['dev', 'test', 'prod']

/** The rows a session outside a repository shows (user decision 09/11/2026; was Replies alone): the rest act on code. */
export const NO_CODE_ROWS = ['Mode', 'Model*', 'Replies', 'Plan', 'Budget', 'Pod', 'Pod message']

export type Item = { key: string; name: string }
export type Row = { label: string; items: Item[] } | { label: string; key: string; names?: Record<string, string> }
const targets = (prefix: string, names = TARGETS): Item[] => names.map(name => ({ key: `${prefix}.${name}`, name }))

/** The lines of a settings block, in order. A setting the schema has and no row names is still drawn (see `block`). */
export const ROWS: Row[] = [
  { label: 'Mode', key: 'mode' },
  // The star ties it to the Agents rows it acts on: the roles whose file says opus carry the same star.
  { label: 'Model*', key: 'mode_model', names: { keep: 'opus' } },
  { label: 'Replies', key: 'reply.length' },
  // `Plan` since 02/11/2026 (was `Steps`, which now names the gate's steps under Gates); the key stays (rule #4).
  // The stored value stays `block` (rule #4); the pane says `force` (user decision 09/11/2026).
  { label: 'Plan', key: 'steps.enforce', names: { block: 'force' } },
  // Shown against the measured spend in Status; it never stops work (user decision 06/11/2026).
  { label: 'Budget', key: 'budget.session_usd', names: { none: 'none' } },
  { label: 'Pod', items: [{ key: 'pod.connect', name: 'on' }] },
  // `Pod message` since 09/11/2026 (was `Format`); the key stays (rule #4).
  { label: 'Pod message', key: 'pod.message_format' },
  { label: 'Tests', items: [{ key: 'write.unit_tests', name: 'unit' }, { key: 'write.e2e', name: 'e2e' }] },
  { label: 'Merge', items: targets('merge') },
  { label: 'Push', items: targets('push') },
  { label: 'Gates', items: targets('gates_before_push') },
  { label: 'Coverage', items: targets('coverage_before_push') },
  { label: 'CI', items: targets('ci_after_push') },
  // Display names only: the stored values stay `hosted` / `self-hosted`, which CI and sdlc_settings.py read.
  { label: 'Runner', key: 'ci.runner', names: { hosted: 'cloud', 'self-hosted': 'local' } },
  { label: 'Deploy', items: targets('deploy_after_push', ['test', 'prod']) },
  { label: 'E2E', items: targets('e2e_before_deploy', ['test', 'prod']) },
]

/** The labels of the Settings rows, in order; every one has a hover card text in help.ts. */
export const ROW_LABELS = ROWS.map(row => row.label)
