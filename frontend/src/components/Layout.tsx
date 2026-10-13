import { useTranslation } from 'react-i18next'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useMe, useMode, type Mode } from '../session'
import { Icon, type IconName } from './Icon'
import { Logo, LogoMark } from './Logo'
import { NotificationBell } from './NotificationBell'

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

  return (
    <div className={`app ${adminMode ? 'admin-mode' : ''}`}>
      <aside className="side">
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
        {adminMode && (
          <div className="mode-banner" role="note">
            <span className="mode-tag">
              <Icon name="shield" small />
              {t('mode.bannerTag')}
            </span>
            <span className="muted">{t('mode.bannerText')}</span>
          </div>
        )}
        <header className="topbar">
          <Link to="/" className="topbar-logo" aria-hidden="true" tabIndex={-1}>
            <LogoMark size={30} />
          </Link>
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
