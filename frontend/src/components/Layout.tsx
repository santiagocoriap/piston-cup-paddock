import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useMe, useMode, type Mode } from '../session'

export function Layout({ onSignOut }: { onSignOut: () => void }) {
  const { t } = useTranslation()
  const me = useMe()
  const { mode } = useMode()
  const adminMode = mode === 'admin'

  return (
    <div className={`app ${adminMode ? 'admin-mode' : ''}`}>
      <header className="topbar">
        <span className="brand">{t('app.name')}</span>
        <nav aria-label={t('nav.main')}>
          <NavLink to="/" end>
            {t('nav.championships')}
          </NavLink>
          {adminMode && me.is_admin && (
            <>
              <NavLink to="/admin/leagues">{t('nav.leagues')}</NavLink>
              <NavLink to="/admin/drivers">{t('nav.drivers')}</NavLink>
              <NavLink to="/admin/catalog">{t('nav.catalog')}</NavLink>
            </>
          )}
          {adminMode && me.can_admin && <NavLink to="/admin/audit">{t('nav.audit')}</NavLink>}
        </nav>
        {me.can_admin && <ModeSwitch />}
        <span className="user">
          {me.username}
          <button type="button" className="secondary" onClick={onSignOut}>
            {t('nav.logout')}
          </button>
        </span>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}

function ModeSwitch() {
  const { t } = useTranslation()
  const { mode, setMode } = useMode()
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
          className={mode === option ? 'on' : ''}
          onClick={() => choose(option)}
        >
          {t(`mode.${option}`)}
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
