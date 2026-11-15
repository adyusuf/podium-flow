import { expect, test } from 'claude-code/testing'

import { commands, fail, fake, ok, STATUS_SCRIPT } from './fake.test'
import { createGlue } from './glue'

// The Promotion and Status boxes' data paths and the interrupted turn, through a fake `$` (F-029).
const REFS = 'dev\ntest\norigin/dev\norigin/test\norigin/prod\n'
type Stage = { branch: string; origin: string; unpushed: number; waived: string[] }
const stages = (store: Map<string, unknown>) => (store.get('promotion') as { stages: Stage[] }).stages

/** git as the Promotion box sees it: `answers` by subcommand, every other call a plain success. */
const git = (answers: Record<string, (argv: readonly string[]) => ReturnType<typeof ok>>) =>
  (argv: readonly string[]) => (answers[argv[1]] ?? (() => ok()))(argv)

test('outside a repository the Promotion box says so and runs no git', async () => {
  const $ = fake()
  $.repo = null
  await createGlue().refreshPromotion($)
  expect($.store.get('promotion')).toEqual({ stages: [], error: 'Not inside a git repository', outside: true })
  expect(commands($)).toEqual([])
})

test('a repository the engine cannot name is not taken as "outside": git still runs', async () => {
  const $ = fake(git({ 'for-each-ref': () => ok('') }))
  $.repo = new Error('no answer')
  await createGlue().refreshPromotion($)
  expect($.store.get('promotion')).toEqual({ stages: [] })
})

test('a failed ref listing is an error, never "outside"', async () => {
  const $ = fake(git({ 'for-each-ref': () => fail('fatal: not a git repository\n', 128) }))
  await createGlue().refreshPromotion($)
  expect($.store.get('promotion')).toEqual({ stages: [], error: 'git failed: fatal: not a git repository' })
})

test('each stage has its origin commit, its unpushed count and the waived gates on the commits waiting to come in', async () => {
  const $ = fake(git({
    'for-each-ref': () => ok(REFS),
    'rev-parse': argv => ok(`${argv.at(-1)!.slice('origin/'.length)}1\n`),
    'rev-list': argv => ok(argv.at(-1) === 'origin/dev..dev' ? '2\n' : '0\n'),
    log: argv => ok(argv.at(-1) === 'origin/prod..origin/test' ? '\0abc1234\nmerge\n\nGate-Waived: e2e (neden: configuration)\n' : ''),
  }))
  await createGlue().refreshPromotion($)
  expect(stages($.store)).toEqual([
    { branch: 'dev', origin: 'dev1', unpushed: 2, waived: [] },
    { branch: 'test', origin: 'test1', unpushed: 0, waived: [] },
    { branch: 'prod', origin: 'prod1', unpushed: 0, waived: ['abc1234 e2e (neden: configuration)'] },
  ])
  // A stage with no local branch is not counted; the first stage has no range to read.
  expect(commands($).filter(one => one.startsWith('rev-list'))).toEqual(['rev-list --count origin/dev..dev', 'rev-list --count origin/test..test'])
  expect(commands($).filter(one => one.startsWith('log'))).toEqual(['log --format=%x00%h%n%B origin/test..origin/dev', 'log --format=%x00%h%n%B origin/prod..origin/test'])
})

const FILE = '/status/s1.json'
const TABLE = JSON.stringify({ now: 'x', rows: [{ item: '1. plan', state: 'running' }] })

test('the Status box reads its file on a new modification time only, and again when asked anew', async () => {
  const $ = fake()
  const glue = createGlue()
  $.files[FILE] = { mtimeMs: 10, text: TABLE }
  await glue.refreshStatus($)
  expect(($.store.get('status') as { rows: unknown[] }).rows.length).toBe(1)
  $.files[FILE] = { mtimeMs: 10, text: '{}' }
  await glue.refreshStatus($)
  expect(($.store.get('status') as { rows: unknown[] }).rows.length).toBe(1)
  await glue.refreshStatus($, true)
  expect(($.store.get('status') as { rows: unknown[] }).rows.length).toBe(0)
})

test('the Status box clears when its file goes away, and reads nothing without a session id', async () => {
  const $ = fake()
  const glue = createGlue()
  $.files[FILE] = { mtimeMs: 10, text: TABLE }
  await glue.refreshStatus($)
  delete $.files[FILE]
  await glue.refreshStatus($)
  expect($.store.get('status')).toBe(null)
  const none = fake()
  none.id = ''
  none.files[FILE] = { mtimeMs: 10, text: TABLE }
  await createGlue().refreshStatus(none)
  expect(none.store.has('status')).toBe(false)
})

test('a Status file that cannot be read keeps the last table and is said once, then read again', async () => {
  const $ = fake()
  const glue = createGlue()
  $.files[FILE] = { mtimeMs: 10, text: TABLE }
  await glue.refreshStatus($)
  $.files[FILE] = new Error('EACCES')
  await glue.refreshStatus($)
  await glue.refreshStatus($)
  expect(($.store.get('status') as { rows: unknown[] }).rows.length).toBe(1)
  expect($.logs).toEqual([`podium: the Status box cannot read ${FILE}; it keeps its last table and tries again`])
  $.files[FILE] = { mtimeMs: 10, text: '{}' }
  await glue.refreshStatus($)
  expect(($.store.get('status') as { rows: unknown[] }).rows.length).toBe(0)
})

test('a Status file that fails while it is read keeps the last table too', async () => {
  const $ = fake()
  const glue = createGlue()
  $.files[FILE] = { mtimeMs: 10, text: TABLE }
  await glue.refreshStatus($)
  $.fs.read = () => Promise.reject(new Error('EIO'))
  $.files[FILE] = { mtimeMs: 11, text: '{}' }
  await glue.refreshStatus($)
  expect(($.store.get('status') as { rows: unknown[] }).rows.length).toBe(1)
  expect($.logs.length).toBe(1)
})

test('after an interrupted turn the status script marks this session as waiting', async () => {
  const $ = fake(() => ok())
  await createGlue().waitAfterInterrupt($)
  expect($.runs.at(-1)).toEqual(['python3', STATUS_SCRIPT, 'hook', 'stop'])
  expect($.stdins).toEqual([JSON.stringify({ session_id: 's1' })])
})

test('two Promotion refreshes that overlap run one after another, never interleaved (F-036)', async () => {
  const answer = git({ 'for-each-ref': () => ok('dev\norigin/dev\norigin/test\n') })
  const $ = fake(async argv => { await new Promise(resolve => setTimeout(resolve, 3)); return answer(argv) })
  const glue = createGlue()
  await Promise.all([glue.refreshPromotion($), glue.refreshPromotion($)])
  const one = ['for-each-ref --format=%(refname:short) refs/heads refs/remotes/origin', 'rev-parse --short origin/dev',
    'rev-list --count origin/dev..dev', 'rev-parse --short origin/test']
  expect(commands($).filter(word => !word.startsWith('log'))).toEqual([...one, ...one])
})

for (const failing of ['rev-parse', 'rev-list', 'log']) {
  test(`a failed git ${failing} marks the stage "could not read", never pushed or free of waived gates (F-035)`, async () => {
    const $ = fake(git({
      'for-each-ref': () => ok('dev\ntest\norigin/dev\norigin/test\n'),
      'rev-parse': () => ok('abc1234\n'),
      'rev-list': () => ok('3\n'),
      log: () => ok('\0abc1234\nGate-Waived: e2e (neden: configuration)\n'),
      [failing]: () => fail(`fatal: bad ${failing}\n`, 128),
    }))
    await createGlue().refreshPromotion($)
    const test = stages($.store).find(stage => stage.branch === 'test')!
    expect(test).toEqual({ branch: 'test', origin: failing === 'rev-parse' ? '' : 'abc1234', unpushed: 0, waived: [],
      unreadable: `git ${failing} failed: fatal: bad ${failing}` })
  })
}

test('a failed git call with no error text still marks the stage "could not read" (F-035)', async () => {
  const $ = fake(git({ 'for-each-ref': () => ok('origin/dev\n'), 'rev-parse': () => fail('', 1) }))
  await createGlue().refreshPromotion($)
  expect(stages($.store)).toEqual([{ branch: 'dev', origin: '', unpushed: 0, waived: [], unreadable: 'git rev-parse failed' }])
})

test('after an interrupted turn with no status script found nothing runs, and it is said once (F-037)', async () => {
  const $ = fake(() => ok())
  $.found = false
  const glue = createGlue()
  await glue.waitAfterInterrupt($)
  await glue.waitAfterInterrupt($)
  expect(commands($)).toEqual([])
  expect($.logs).toEqual(['podium: no podium_status.py found, so the Status box was not marked as waiting after the interrupted turn'])
})

test('a status script that fails to mark the session as waiting is said in the log (F-037)', async () => {
  const $ = fake(() => fail('Traceback: bad payload\n'))
  await createGlue().waitAfterInterrupt($)
  expect($.logs).toEqual(['podium: marking the Status box as waiting failed: Traceback: bad payload'])
  const silent = fake(() => fail('', 3))
  await createGlue().waitAfterInterrupt(silent)
  expect(silent.logs).toEqual(['podium: marking the Status box as waiting failed: exit 3'])
})
