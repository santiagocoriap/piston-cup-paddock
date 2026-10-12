import { describe, expect, it } from 'vitest'
import en from './en.json'
import es from './es.json'

function keys(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix]
  return Object.entries(value).flatMap(([key, child]) => keys(child, prefix ? `${prefix}.${key}` : key))
}

describe('translations', () => {
  it('Spanish and English have the same keys', () => {
    expect(keys(en).sort()).toEqual(keys(es).sort())
  })
})
