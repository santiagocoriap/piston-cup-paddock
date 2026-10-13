import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useMe, useMode, type Mode } from '../session'
import { Icon, type IconName } from './Icon'
import { Logo, LogoMark } from './Logo'
import { NotificationBell } from './NotificationBell'

const SIDE_KEY = 'paddock.side'

function readSide(): boolean {
  try {
    return localStorage.getItem(SIDE_KEY) === 'hidden'
  } catch {
    return false
  }
}

/** True above the phone width. On a phone the side menu is the bottom bar and never hides. */
function useWide(): boolean {
  const query = '(min-width: 701px)'
  const [wide, setWide] = useState(() => (typeof window.matchMedia === 'function' ? window.matchMedia(query).matches : true))
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const list = window.matchMedia(query)
    const update = () => setWide(list.matches)
    list.addEventListener('change', update)
    return () => list.removeEventListener('change', update)
  }, [])
  return wide
}

function NavItem({ to, icon, label, end }: { to: string; icon: IconName; label: string; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}>
      <Icon name={icon} />
      <span>{label}</span>
    </NavLink>
  )
}

export function Layout({ onSignOut }: { onSignOut: () => void }) {
  const { t } = useTranslation()
  const me = useMe()
  const { mode, setMode } = useMode()
  const adminMode = mode === 'admin'
  const initials = me.username.slice(0, 2).toUpperCase()
  const [sideHidden, setSideHidden] = useState(() => readSide())
  const wide = useWide()

  function toggleSide() {
    const next = !sideHidden
    setSideHidden(next)
    try {
      localStorage.setItem(SIDE_KEY, next ? 'hidden' : 'shown')
    } catch {
      // Private windows can refuse storage. The choice then lasts for this page only.
    }
  }

  return (
    <div className={`app ${adminMode ? 'admin-mode' : ''} ${sideHidden ? 'side-hidden' : ''}`}>
      <aside className="side" id="side-panel" inert={sideHidden && wide ? true : undefined}>
        <Link to="/" className="side-logo" aria-label={t('app.name')}>
          <Logo />
        </Link>
        <nav className="side-nav" aria-label={t('nav.main')}>
          <NavItem to="/" end icon="home" label={t('nav.home')} />
          <NavItem to="/records" icon="timer" label={t('nav.records')} />
          {adminMode && (me.is_admin || me.can_manage) && (
            <p className="group" aria-hidden="true">
              {t('mode.admin')}
            </p>
          )}
          {adminMode && me.is_admin && (
            <>
              <NavItem to="/admin/leagues" icon="layers" label={t('nav.leagues')} />
              <NavItem to="/admin/drivers" icon="users" label={t('nav.drivers')} />
              <NavItem to="/admin/catalog" icon="map" label={t('nav.catalog')} />
            </>
          )}
          {adminMode && me.can_manage && <NavItem to="/admin/accounts" icon="shield" label={t('nav.accounts')} />}
          {adminMode && me.can_manage && <NavItem to="/admin/audit" icon="history" label={t('nav.audit')} />}
        </nav>
        <div className="side-foot">
          <NavLink to="/account" className="me" aria-label={t('nav.account')}>
            <span className="avatar" aria-hidden="true">
              {initials}
            </span>
            <div>
              <b>{me.username}</b>
              <small>{t('nav.account')}</small>
            </div>
          </NavLink>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="icon-button side-toggle"
            aria-controls="side-panel"
            aria-expanded={!sideHidden}
            aria-label={sideHidden ? t('nav.showSide') : t('nav.hideSide')}
            title={sideHidden ? t('nav.showSide') : t('nav.hideSide')}
            onClick={toggleSide}
          >
            <Icon name="panel" />
          </button>
          {sideHidden && (
            <Link to="/" className="side-hidden-logo" aria-label={t('app.name')}>
              <LogoMark size={30} />
            </Link>
          )}
          <Link to="/" className="topbar-logo" aria-hidden="true" tabIndex={-1}>
            <LogoMark size={30} />
          </Link>
          {adminMode && (
            <p className="mode-banner" role="note">
              <span className="mode-tag">
                <Icon name="shield" small />
                {t('mode.bannerTag')}
              </span>
              <span className="mode-text muted">{t('mode.bannerText')}</span>
            </p>
          )}
          <span className="spacer" />
          {me.can_admin && <ModeSwitch mode={mode} setMode={setMode} />}
          <NotificationBell />
          <button
            type="button"
            className="icon-button"
            aria-label={t('nav.logout')}
            title={t('nav.logout')}
            onClick={onSignOut}
          >
            <Icon name="logout" />
          </button>
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
