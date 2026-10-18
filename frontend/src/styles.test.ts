/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// Vitest does not load CSS files, so the test reads the file from disk (the frontend folder).
const css = readFileSync('src/index.css', 'utf8')

// Class names that only mark an element for tests or for a parent rule. They need no own style.
const HOOKS = new Set([
  'admin-panel', 'board', 'briefing', 'evidence', 'hero-main', 'legend', 'report', 'result-form',
  'round-tools', 'scale', 'season-page', 'status-title', 'unmatched', 'voters',
])

const sources = import.meta.glob<string>(['./**/*.tsx', '!./**/*.test.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
})

describe('index.css', () => {
  it('styles every class name that the pages use', () => {
    const defined = new Set([...css.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1]))
    const missing = new Set<string>()
    for (const text of Object.values(sources)) {
      for (const match of text.matchAll(/className=(?:"([^"]+)"|\{`([^`]+)`\})/g)) {
        const value = (match[1] ?? match[2]).replace(/\$\{[^}]*\}/g, ' ')
        for (const name of value.split(/\s+/)) {
          // A name that ends with "-" is the start of a name built in code, for example "state-".
          if (name && !name.endsWith('-') && !HOOKS.has(name) && !defined.has(name)) missing.add(name)
        }
      }
    }
    expect(Object.keys(sources).length).toBeGreaterThan(20)
    expect([...missing].sort()).toEqual([])
  })
})
