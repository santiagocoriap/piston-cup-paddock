import type { KeyboardEvent } from 'react'
import { panelId, tabId } from '../lib/tabs'

export type TabItem = { id: string; label: string; count?: number; warn?: boolean }

type Props = { label: string; idPrefix: string; tabs: TabItem[]; active: string; onChange: (id: string) => void }

/** A row of tabs with a count on each. The arrow keys, Home, and End move between tabs. */
export function Tabs({ label, idPrefix, tabs, active, onChange }: Props) {
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex((tab) => tab.id === active)
    const moves: Record<string, number> = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index - 1 + tabs.length) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    }
    const next = moves[event.key]
    if (next === undefined) return
    event.preventDefault()
    onChange(tabs[next].id)
    document.getElementById(tabId(idPrefix, tabs[next].id))?.focus()
  }

  return (
    <div className="tab-row" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {tabs.map((tab) => {
        const selected = tab.id === active
        return (
          <button
            key={tab.id}
            id={tabId(idPrefix, tab.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={panelId(idPrefix, tab.id)}
            tabIndex={selected ? 0 : -1}
            className="tab"
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
            {tab.count !== undefined && <span className={tab.warn ? 'tab-count warn' : 'tab-count'}>{tab.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
