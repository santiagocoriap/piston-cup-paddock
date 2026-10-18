import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Icon, type IconName } from './Icon'

type Hit = components['schemas']['SearchHitOut']
export type PageLink = { to: string; icon: IconName; label: string }
type Item = { key: string; group: string; to: string; icon: IconName; label: string; detail: string }

const KIND_ICONS: Record<string, IconName> = { championship: 'trophy', season: 'layers', round: 'flag', driver: 'user' }
const KIND_ORDER = ['championship', 'season', 'round', 'driver']
const MIN_LENGTH = 2

/** The search in the header. Ctrl+K or Cmd+K opens it. The arrow keys move, and Enter opens. */
export function CommandMenu({ pages }: { pages: PageLink[] }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<Hit[]>([])
  const [active, setActive] = useState(0)
  const dialog = useRef<HTMLDialogElement>(null)
  const listId = useId()

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    // jsdom has no showModal, so the tests use the open attribute.
    if (open && !element.open) {
      if (typeof element.showModal === 'function') element.showModal()
      else element.setAttribute('open', '')
    } else if (!open && element.open) {
      if (typeof element.close === 'function') element.close()
      else element.removeAttribute('open')
    }
  }, [open])

  // Ask the server after a short pause in the typing. A newer query wins.
  useEffect(() => {
    const text = query.trim()
    if (text.length < MIN_LENGTH) return
    let current = true
    const timer = window.setTimeout(() => {
      api.GET('/api/search', { params: { query: { q: text } } }).then(({ data }) => {
        if (current && data) setHits(data)
      })
    }, 200)
    return () => {
      current = false
      window.clearTimeout(timer)
    }
  }, [query])

  const needle = query.trim().toLowerCase()
  const items: Item[] = [
    ...pages
      .filter((page) => page.label.toLowerCase().includes(needle))
      .map((page) => ({ key: `page-${page.to}`, group: 'pages', to: page.to, icon: page.icon, label: page.label, detail: '' })),
    ...(needle.length >= MIN_LENGTH ? hits : [])
      .slice()
      .sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind))
      .map((hit) => ({
        key: `${hit.kind}-${hit.path}`,
        group: hit.kind,
        to: hit.path,
        icon: KIND_ICONS[hit.kind] ?? 'arrow',
        label: hit.number === null ? hit.label : `${t('round.title', { number: hit.number })} · ${hit.label}`,
        detail: hit.detail,
      })),
  ]

  function close() {
    setOpen(false)
    setQuery('')
    setHits([])
    setActive(0)
  }

  function go(item: Item | undefined) {
    if (!item) return
    close()
    navigate(item.to)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive((old) => (items.length === 0 ? 0 : (old + step + items.length) % items.length))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      go(items[active])
    }
  }

  return (
    <>
      <button
        type="button"
        className="search-trigger"
        aria-keyshortcuts="Control+K Meta+K"
        aria-label={t('nav.search')}
        onClick={() => setOpen(true)}
      >
        <Icon name="search" small />
        <span className="search-trigger-text">{t('nav.search')}</span>
        <kbd>{t('nav.searchShortcut')}</kbd>
      </button>
      <dialog
        ref={dialog}
        className="command-dialog"
        aria-label={t('nav.search')}
        onClose={close}
        onClick={(event) => {
          if (event.target === event.currentTarget) close()
        }}
      >
        {open && (
          <div className="command-box">
            <div className="command-input">
              <Icon name="search" />
              <input
                autoFocus
                role="combobox"
                aria-expanded="true"
                aria-controls={listId}
                aria-autocomplete="list"
                aria-activedescendant={items[active] ? `${listId}-${active}` : undefined}
                aria-label={t('nav.search')}
                placeholder={t('nav.searchPlaceholder')}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value)
                  setActive(0)
                }}
                onKeyDown={onKeyDown}
              />
              <kbd>Esc</kbd>
            </div>
            <ul id={listId} role="listbox" aria-label={t('nav.search')} className="command-list">
              {items.map((item, index) => (
                <li key={item.key} role="presentation">
                  {(index === 0 || items[index - 1].group !== item.group) && (
                    <p className="command-group" aria-hidden="true">
                      {t(`nav.searchGroups.${item.group}`)}
                    </p>
                  )}
                  <div
                    id={`${listId}-${index}`}
                    role="option"
                    aria-selected={index === active}
                    className={index === active ? 'command-item active' : 'command-item'}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => go(item)}
                  >
                    <Icon name={item.icon} small />
                    <span className="command-label">{item.label}</span>
                    {item.detail && <span className="command-detail">{item.detail}</span>}
                  </div>
                </li>
              ))}
            </ul>
            {items.length === 0 && <p className="command-empty muted">{t('nav.searchEmpty', { query: query.trim() })}</p>}
            {needle.length < MIN_LENGTH && <p className="command-hint muted">{t('nav.searchHint')}</p>}
          </div>
        )}
      </dialog>
    </>
  )
}
