import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { api, type Me } from './api/client'
import { Layout } from './components/Layout'
import { AuditPage } from './pages/admin/AuditPage'
import { CatalogPage } from './pages/admin/CatalogPage'
import { DriversPage } from './pages/admin/DriversPage'
import { LeaguesPage } from './pages/admin/LeaguesPage'
import { ChampionshipPage } from './pages/ChampionshipPage'
import { ChampionshipsPage } from './pages/ChampionshipsPage'
import { RoundPage } from './pages/RoundPage'
import { SeasonPage } from './pages/SeasonPage'
import { useMode } from './session'
import { SessionProvider } from './SessionProvider'

type Session = { status: 'loading' } | { status: 'anonymous' } | { status: 'signed-in'; me: Me }

export default function App() {
  const { t, i18n } = useTranslation()
  const [session, setSession] = useState<Session>({ status: 'loading' })

  useEffect(() => {
    api.GET('/api/auth/me').then(({ data }) => {
      setSession(data ? { status: 'signed-in', me: data } : { status: 'anonymous' })
    })
  }, [])

  useEffect(() => {
    if (session.status === 'signed-in') void i18n.changeLanguage(session.me.language)
  }, [session, i18n])

  async function signOut() {
    await api.POST('/api/auth/logout')
    setSession({ status: 'anonymous' })
  }

  if (session.status !== 'signed-in') {
    return (
      <div className="shell narrow">
        <header className="brand">{t('app.name')}</header>
        {session.status === 'loading' ? (
          <p>{t('app.loading')}</p>
        ) : (
          <LoginForm onSignedIn={(me) => setSession({ status: 'signed-in', me })} />
        )}
      </div>
    )
  }

  return (
    <SessionProvider me={session.me}>
      <BrowserRouter>
        <AppRoutes isAdmin={session.me.is_admin} canAdmin={session.me.can_admin} onSignOut={signOut} />
      </BrowserRouter>
    </SessionProvider>
  )
}

function AppRoutes({
  isAdmin,
  canAdmin,
  onSignOut,
}: {
  isAdmin: boolean
  canAdmin: boolean
  onSignOut: () => void
}) {
  const { mode } = useMode()
  const adminPages = isAdmin && mode === 'admin'
  const managerPages = canAdmin && mode === 'admin'
  return (
    <Routes>
      <Route element={<Layout onSignOut={onSignOut} />}>
        <Route index element={<ChampionshipsPage />} />
        <Route path="championships/:championshipId" element={<ChampionshipPage />} />
        <Route path="seasons/:seasonId" element={<SeasonPage />} />
        <Route path="rounds/:roundId" element={<RoundPage />} />
        {adminPages && <Route path="admin/leagues" element={<LeaguesPage />} />}
        {adminPages && <Route path="admin/drivers" element={<DriversPage />} />}
        {adminPages && <Route path="admin/catalog" element={<CatalogPage />} />}
        {managerPages && <Route path="admin/audit" element={<AuditPage />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

function LoginForm({ onSignedIn }: { onSignedIn: (me: Me) => void }) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const form = new FormData(event.currentTarget)
    await api.GET('/api/auth/csrf')
    const { data, response } = await api.POST('/api/auth/login', {
      body: { username: String(form.get('username')), password: String(form.get('password')) },
    })
    if (data && 'username' in data) onSignedIn(data)
    else setError(response.status === 401 ? t('login.invalid') : t('login.error'))
  }

  return (
    <form className="card" onSubmit={submit}>
      <h1>{t('login.title')}</h1>
      <label>
        {t('login.username')}
        <input name="username" autoComplete="username" required />
      </label>
      <label>
        {t('login.password')}
        <input name="password" type="password" autoComplete="current-password" required />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button type="submit">{t('login.submit')}</button>
    </form>
  )
}
