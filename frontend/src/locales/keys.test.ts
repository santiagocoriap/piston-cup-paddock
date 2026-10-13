import { describe, expect, it } from 'vitest'
import en from './en.json'
import es from './es.json'

// Vite loads the source text of every file, so the test needs no Node.js API.
const sources = import.meta.glob<string>(['../**/*.ts', '../**/*.tsx', '!../**/*.test.ts', '!../**/*.test.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
})

function has(texts: unknown, key: string): boolean {
  let node: unknown = texts
  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null) return false
    const record = node as Record<string, unknown>
    // i18next plural keys: "count_one" and "count_other" answer for "count".
    node = record[part] ?? record[`${part}_other`]
  }
  return node !== undefined
}

/** Every fixed key in t('...') must exist in both languages. Keys with ${...} are dynamic. */
describe('translation keys', () => {
  const used = new Set<string>()
  for (const text of Object.values(sources)) {
    for (const match of text.matchAll(/\bt\(\s*'([a-zA-Z0-9_.]+)'/g)) used.add(match[1])
  }

  it('finds the keys in the code', () => {
    expect(used.size).toBeGreaterThan(300)
    expect(used).toContain('calendar.fixed')
  })

  it.each([
    ['es', es],
    ['en', en],
  ])('%s has every key', (_, texts) => {
    const missing = [...used].filter((key) => !has(texts, key)).sort()
    expect(missing).toEqual([])
  })
})
