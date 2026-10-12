import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type Me } from './api/client'

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

  return (
    <main className="shell">
      <header className="brand">{t('app.name')}</header>
      {session.status === 'loading' && <p>{t('app.loading')}</p>}
      {session.status === 'anonymous' && (
        <LoginForm onSignedIn={(me) => setSession({ status: 'signed-in', me })} />
      )}
      {session.status === 'signed-in' && (
        <Home me={session.me} onSignedOut={() => setSession({ status: 'anonymous' })} />
      )}
    </main>
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

function Home({ me, onSignedOut }: { me: Me; onSignedOut: () => void }) {
  const { t } = useTranslation()

  async function signOut() {
    await api.POST('/api/auth/logout')
    onSignedOut()
  }

  return (
    <section className="card">
      <h1>{t('home.welcome', { name: me.username })}</h1>
      <p>{t('home.intro')}</p>
      <button type="button" onClick={signOut}>
        {t('home.logout')}
      </button>
    </section>
  )
}
