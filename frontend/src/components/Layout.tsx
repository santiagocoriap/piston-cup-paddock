import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { useLoad } from '../lib/useLoad'
import { useMe, useMode, type Mode } from '../session'
import { CommandMenu } from './CommandMenu'
import { Icon, type IconName } from './Icon'
import { Logo, LogoMark } from './Logo'
import { NotificationBell } from './NotificationBell'
import { UserMenu } from './UserMenu'

const SIDE_KEY = 'paddock.side'

// "hidden" is the old name of the narrow menu. A browser that kept it opens with the icon rail.
function readRail(): boolean {
  try {
    return localStorage.getItem(SIDE_KEY) === 'hidden'
  } catch {
    return false
  }
}

type NavEntry = { to: string; icon: IconName; label: string; end?: boolean; count?: number }

function NavItem({ to, icon, label, end, count }: NavEntry) {
  const { t } = useTranslation()
  return (
    <NavLink
      to={to}
      end={end}
      data-label={label}
      className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}
    >
      <Icon name={icon} />
      <span className="nav-label">{label}</span>
      {count !== undefined && count > 0 && (
        <span className="nav-count">
          <span aria-hidden="true">{count}</span>
          <span className="sr-only">{`, ${t('nav.pendingCount', { count })}`}</span>
        </span>
      )}
    </NavLink>
  )
}

type Pending = components['schemas']['PendingOut']

export function Layout({ onSignOut }: { onSignOut: () => void }) {
  const { t } = useTranslation()
  const me = useMe()
  const { mode, setMode } = useMode()
  const { pathname } = useLocation()
  const adminMode = mode === 'admin'
  const [rail, setRail] = useState(() => readRail())
  const showPending = adminMode && (me.is_admin || me.can_manage)
  // The counts come again on each page change, so a count drops right after the work.
  const pending = useLoad(
    () => (showPending ? api.GET('/api/pending') : Promise.resolve({ data: [] as Pending[] })),
    [showPending, pathname],
  )
  const count = (...kinds: string[]) =>
    (pending.data ?? []).filter((item) => kinds.includes(item.kind)).reduce((sum, item) => sum + item.count, 0)

  function toggleRail() {
    const next = !rail
    setRail(next)
    try {
      localStorage.setItem(SIDE_KEY, next ? 'hidden' : 'shown')
    } catch {
      // Private windows can refuse storage. The choice then lasts for this page only.
    }
  }

  const main: NavEntry[] = [
    { to: '/', end: true, icon: 'home', label: t('nav.home'), count: count('results', 'protests', 'ballots_closed') },
    { to: '/records', icon: 'timer', label: t('nav.records') },
  ]
  const admin: NavEntry[] = [
    ...(adminMode && me.is_admin
      ? [
          { to: '/admin/leagues', icon: 'layers' as const, label: t('nav.leagues') },
          { to: '/admin/drivers', icon: 'users' as const, label: t('nav.drivers') },
          { to: '/admin/catalog', icon: 'map' as const, label: t('nav.catalog'), count: count('images') },
        ]
      : []),
    ...(adminMode && me.can_manage
      ? [
          { to: '/admin/accounts', icon: 'shield' as const, label: t('nav.accounts'), count: count('accounts') },
          { to: '/admin/audit', icon: 'history' as const, label: t('nav.audit') },
        ]
      : []),
  ]
  const pages = [...main, ...admin, { to: '/account', icon: 'user' as const, label: t('nav.account') }]

  return (
    <div className={`app ${adminMode ? 'admin-mode' : ''} ${rail ? 'side-rail' : ''}`}>
      <aside className="side" id="side-panel">
        <Link to="/" className="side-logo" aria-label={t('app.name')}>
          <Logo />
        </Link>
        <nav className="side-nav" aria-label={t('nav.main')}>
          {main.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
          {admin.length > 0 && (
            <p className="group" aria-hidden="true">
              {t('mode.admin')}
            </p>
          )}
          {admin.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </nav>
        <div className="side-foot">
          <UserMenu onSignOut={onSignOut} placement="up" />
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="icon-button side-toggle"
            aria-controls="side-panel"
            aria-expanded={!rail}
            aria-label={rail ? t('nav.expandSide') : t('nav.collapseSide')}
            title={rail ? t('nav.expandSide') : t('nav.collapseSide')}
            onClick={toggleRail}
          >
            <Icon name="panel" />
          </button>
          <Link to="/" className="topbar-logo" aria-hidden="true" tabIndex={-1}>
            <LogoMark size={30} />
          </Link>
          {adminMode && (
            <p className="mode-banner" role="note">
              <span className="mode-tag" title={t('mode.bannerText')}>
                <Icon name="shield" small />
                <span className="mode-tag-text">{t('mode.bannerShort')}</span>
              </span>
              <span className="sr-only">{t('mode.bannerText')}</span>
            </p>
          )}
          <span className="spacer" />
          <CommandMenu pages={pages} />
          {me.can_admin && <ModeSwitch mode={mode} setMode={setMode} />}
          <NotificationBell />
          {/* On a phone the side menu is the bottom bar, so the account menu is here. */}
          <UserMenu onSignOut={onSignOut} placement="down" className="topbar-user" />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function ModeSwitch({ mode, setMode }: { mode: Mode; setMode: (mode: Mode) => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()

  function choose(next: Mode) {
    setMode(next)
    // The admin pages do not exist in the driver mode.
    if (next === 'driver' && pathname.startsWith('/admin')) navigate('/')
  }

  return (
    <div className="mode-switch" role="group" aria-label={t('mode.label')}>
      {(['driver', 'admin'] as const).map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={mode === option}
          aria-label={t(`mode.${option}`)}
          className={mode === option ? 'on' : ''}
          onClick={() => choose(option)}
        >
          <Icon name={option === 'driver' ? 'user' : 'shield'} small />
          <span>{t(`mode.${option}Short`)}</span>
        </button>
      ))}
    </div>
  )
}

/** Show a loading or error line until the data is there. */
export function Loading({ failed }: { failed: boolean }) {
  const { t } = useTranslation()
  return failed ? <p role="alert">{t('app.loadFailed')}</p> : <p>{t('app.loading')}</p>
}
