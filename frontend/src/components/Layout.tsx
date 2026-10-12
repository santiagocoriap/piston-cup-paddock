import { useTranslation } from 'react-i18next'
import { NavLink, Outlet } from 'react-router'
import { useMe } from '../session'

export function Layout({ onSignOut }: { onSignOut: () => void }) {
  const { t } = useTranslation()
  const me = useMe()

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">{t('app.name')}</span>
        <nav aria-label={t('app.name')}>
          <NavLink to="/" end>
            {t('nav.championships')}
          </NavLink>
          {me.is_admin && (
            <>
              <NavLink to="/admin/leagues">{t('nav.leagues')}</NavLink>
              <NavLink to="/admin/drivers">{t('nav.drivers')}</NavLink>
              <NavLink to="/admin/catalog">{t('nav.catalog')}</NavLink>
            </>
          )}
        </nav>
        <span className="user">
          {me.username}
          <button type="button" className="secondary" onClick={onSignOut}>
            {t('nav.logout')}
          </button>
        </span>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  )
}

/** Show a loading or error line until the data is there. */
export function Loading({ failed }: { failed: boolean }) {
  const { t } = useTranslation()
  return failed ? <p role="alert">{t('app.loadFailed')}</p> : <p>{t('app.loading')}</p>
}
