import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { initials } from '../lib/initials'
import { applyTheme, readTheme, type Theme } from '../lib/theme'
import { useMe } from '../session'
import { Icon } from './Icon'

type Props = { onSignOut: () => void; placement: 'up' | 'down'; className?: string }

/** The account menu: the user, "Mi cuenta", the color theme, and "Cerrar sesión". */
export function UserMenu({ onSignOut, placement, className = '' }: Props) {
  const { t } = useTranslation()
  const me = useMe()
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState<Theme>(() => readTheme())
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const role = me.is_admin ? t('nav.roleLeagueAdmin') : me.can_manage ? t('nav.roleAdmin') : t('nav.roleDriver')

  useEffect(() => {
    if (!open) return
    root.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
    const outside = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [open])

  function close() {
    setOpen(false)
    trigger.current?.focus()
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const items = [...(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])]
    const index = items.indexOf(document.activeElement as HTMLElement)
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      items[(index + step + items.length) % items.length]?.focus()
    }
  }

  function switchTheme() {
    const next: Theme = theme === 'noche' ? 'dia' : 'noche'
    applyTheme(next)
    setTheme(next)
  }

  return (
    <div className={`user-menu ${placement} ${className}`.trim()} ref={root} onKeyDown={onKeyDown}>
      <button
        ref={trigger}
        type="button"
        className="me"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('nav.userMenu', { name: me.username })}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="avatar" aria-hidden="true">
          {initials(me.username)}
        </span>
        <span className="me-text">
          <b>{me.username}</b>
          <small>{role}</small>
        </span>
        <span className="me-chevron" aria-hidden="true">
          <Icon name="chevron" small />
        </span>
      </button>
      {open && (
        <div className="user-menu-panel" role="menu" aria-label={t('nav.userMenu', { name: me.username })}>
          <p className="user-menu-head">
            <b>{me.username}</b>
            <small>{role}</small>
          </p>
          <Link role="menuitem" to="/account" className="menu-item" onClick={() => setOpen(false)}>
            <Icon name="user" small />
            {t('nav.account')}
          </Link>
          <button type="button" role="menuitem" className="menu-item" onClick={switchTheme}>
            <Icon name={theme === 'noche' ? 'sun' : 'moon'} small />
            {theme === 'noche' ? t('nav.themeDay') : t('nav.themeNight')}
          </button>
          <hr />
          <button type="button" role="menuitem" className="menu-item danger-item" onClick={onSignOut}>
            <Icon name="logout" small />
            {t('nav.logout')}
          </button>
        </div>
      )}
    </div>
  )
}
