import { expect, test } from 'claude-code/testing'

import { commands, configScript, fail, fake, later, ok, type Layers } from './fake.test'
import { createGlue } from './glue'
import { safely } from './port'

// The Settings box's data paths through a fake `$` (F-029): what a press runs and says, and what a refresh stores.
const layers = (over: Partial<Layers> = {}): Layers => ({ saved: { mode: 'C', 'push.prod': true }, session: {}, project: {}, ...over })
const READ = ['show --json --session s1', 'agents --json --all --session s1', 'schema', 'show --json --user']

test('a refresh reads the four answers of the installed script and stores the settings, with no error', async () => {
  const $ = fake(configScript(layers()))
  await createGlue().refreshSettings($)
  expect(commands($)).toEqual(READ)
  expect(($.store.get('settings') as { values: unknown }).values).toEqual({ mode: 'C', 'push.prod': true })
  expect(($.store.get('settings') as { saved: { values: unknown } }).saved.values).toEqual({ mode: 'C', 'push.prod': true })
  expect($.store.get('settingsError')).toBe('')
  expect($.store.get('settingsProblems')).toEqual([])
})

test('a refresh with no installed plugin says so and runs nothing else', async () => {
  const $ = fake(configScript(layers()))
  $.found = false
  await createGlue().refreshSettings($)
  expect(commands($)).toEqual([])
  expect(String($.store.get('settingsError'))).toContain('not installed yet')
})

test('a refresh with no session id reads the effective settings without a session layer', async () => {
  const $ = fake(configScript(layers()))
  $.id = new Error('no session')
  await createGlue().refreshSettings($)
  expect(commands($)[0]).toBe('show --json')
})

for (const [at, word] of READ.entries()) {
  test(`a refresh whose "${word}" fails keeps the last settings and shows that command's error`, async () => {
    const script = configScript(layers())
    const $ = fake(argv => (argv.slice(2).join(' ') === word ? fail(`boom ${at}`) : script(argv)))
    $.store.set('settings', 'before')
    await createGlue().refreshSettings($)
    expect($.store.get('settings')).toBe('before')
    expect($.store.get('settingsError')).toBe(`boom ${at}`)
  })
}

test('a refresh whose answers fail with no error text says the script failed', async () => {
  const $ = fake(() => fail(''))
  await createGlue().refreshSettings($)
  expect($.store.get('settingsError')).toBe('podium_config.py failed')
})

test('an unreadable answer is said in the Settings box and keeps the last settings', async () => {
  const $ = fake(argv => (argv[2] === 'schema' ? ok('not json') : configScript(layers())(argv)))
  $.store.set('settings', 'before')
  await createGlue().refreshSettings($)
  expect($.store.get('settings')).toBe('before')
  expect(String($.store.get('settingsError'))).toContain('Unreadable answer from podium_config.py')
})

test('a change since the last read is one warning line in the chat; the first read says nothing', async () => {
  const config = layers()
  const $ = fake(configScript(config))
  const glue = createGlue()
  await glue.refreshSettings($)
  expect($.logs).toEqual([])
  config.project.mode = 'B'
  await glue.refreshSettings($)
  expect($.logs.length).toBe(1)
  expect($.logs[0]).toContain('Mode (mode) C → B')
})

test('a failing read never stops the hook: the Settings box says what failed', async () => {
  const $ = fake()
  await safely($, Promise.reject(new Error('spawn failed')))
  expect($.store.get('settingsError')).toBe('Could not read: Error: spawn failed')
})

test('a press with no installed plugin says so and writes nothing', async () => {
  const $ = fake(configScript(layers()))
  $.found = false
  await createGlue().click($, 'mode', 'B', 'session')
  expect(commands($)).toEqual([])
  expect($.toasts).toEqual(['The podium plugin is not installed yet: /plugin install podium@podium-marketplace'])
})

test('a press on the Session tab with no session id changes nothing, not even the saved defaults', async () => {
  const $ = fake(configScript(layers()))
  $.id = ''
  await createGlue().click($, 'mode', 'B', 'session')
  expect(commands($)).toEqual([])
  expect($.toasts[0]).toContain('Could not tell which session this is')
})

test('a press writes this session, or the saved defaults on the System tab, then reads again', async () => {
  const config = layers()
  const $ = fake(configScript(config))
  const glue = createGlue()
  await glue.click($, 'mode', 'B', 'session')
  await glue.click($, 'push.prod', 'no', 'saved')
  expect(commands($)).toEqual(['set --session s1 mode B', ...READ, 'set push.prod no', ...READ])
  expect(config.session).toEqual({ mode: 'B' })
  expect(config.saved['push.prod']).toBe(false)
  expect($.toasts).toEqual([])
})

test('a refused press shows the script\'s error and still reads again; no override note follows it', async () => {
  const script = configScript(layers())
  const $ = fake(argv => (argv[2] === 'set' ? fail('mode: Z is not one of A, B, C\n') : script(argv)))
  await createGlue().click($, 'mode', 'Z', 'session')
  expect($.toasts).toEqual(['mode: Z is not one of A, B, C'])
  expect(commands($).slice(1)).toEqual(READ)
})

test('a refused press with no error text says it was refused', async () => {
  const script = configScript(layers())
  const $ = fake(argv => (argv[2] === 'set' ? fail('') : script(argv)))
  await createGlue().click($, 'mode', 'B', 'saved')
  expect($.toasts).toEqual(['The change was refused'])
})

test('a press a higher layer overrides says which layer wins', async () => {
  const $ = fake(configScript(layers({ project: { mode: 'D' } })))
  await createGlue().click($, 'mode', 'B', 'session')
  expect($.toasts).toEqual(["mode stays D: the project layer sets it, and it wins over the user's file"])
})

test('two quick presses run one after another, in the order pressed', async () => {
  const script = configScript(layers())
  const events: string[] = []
  const $ = fake(async argv => {
    if (argv[2] !== 'set') return script(argv)
    events.push(`start ${argv.at(-2)}`)
    await later()
    events.push(`end ${argv.at(-2)}`)
    return script(argv)
  })
  const glue = createGlue()
  void glue.click($, 'mode', 'B', 'session')
  await glue.click($, 'push.prod', 'no', 'session')
  expect(events).toEqual(['start mode', 'end mode', 'start push.prod', 'end push.prod'])
})

test('a press whose run is rejected says so in a toast and the log, and the next press still runs (F-030)', async () => {
  const script = configScript(layers())
  let spawn = false
  const $ = fake(argv => {
    if (argv[2] === 'set' && !spawn) { spawn = true; throw new Error('spawn python3 ENOENT') }
    return script(argv)
  })
  const glue = createGlue()
  await glue.click($, 'mode', 'B', 'session')
  expect($.toasts).toEqual(['The change could not be made: Error: spawn python3 ENOENT'])
  expect($.logs).toEqual(['podium: a press in the Settings box failed: Error: spawn python3 ENOENT'])
  await glue.click($, 'mode', 'B', 'session')
  expect(commands($).filter(one => one.startsWith('set')).length).toBe(2)
})
