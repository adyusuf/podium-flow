// Stands in for the engine's 'claude-code/testing' when the mod's engine-free logic is measured with Deno
// (scripts/coverage.sh): the same `test` and `expect(...).toBe/.toEqual/.toContain/.toBeDefined` the mod's tests use,
// nothing more. A matcher the tests start using must be added here too, or the coverage step fails type-checking.
import assert from 'node:assert/strict'

export const test = (name: string, body: () => void | Promise<void>) => Deno.test(name, body)

const contains = (actual: unknown, part: unknown) => String(actual).includes(String(part))

export const expect = (actual: unknown) => ({
  toBe: (wanted: unknown) => assert.strictEqual(actual, wanted),
  toEqual: (wanted: unknown) => assert.deepStrictEqual(actual, wanted),
  toContain: (part: string) => assert.ok(contains(actual, part), `${String(actual)} does not contain ${part}`),
  toBeDefined: () => assert.notStrictEqual(actual, undefined),
  // The negations the tests use (14/11/2026: two status tests used `.not.toContain`, which failed type-checking and made
  // the coverage step red for the whole repository — test inventory F-042).
  not: {
    toBe: (wanted: unknown) => assert.notStrictEqual(actual, wanted),
    toEqual: (wanted: unknown) => assert.notDeepStrictEqual(actual, wanted),
    toContain: (part: string) => assert.ok(!contains(actual, part), `${String(actual)} contains ${part}`),
  },
})
