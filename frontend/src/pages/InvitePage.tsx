import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { errorMessage } from '../lib/errors'

/** The page of a one-time link. The token is after "#", so the server logs never see it. */
export function InvitePage({ onSignedIn }: { onSignedIn: () => void }) {
  const { t } = useTranslation()
  const [token] = useState(() => window.location.hash.slice(1))
  const [info, setInfo] = useState<{ username: string; purpose: string } | null | 'invalid'>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.POST('/api/auth/invite/check', { body: { token } }).then(({ data }) => {
      setInfo(data ?? 'invalid')
    })
  }, [token])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const form = new FormData(event.currentTarget)
    await api.GET('/api/auth/csrf')
    const { error } = await api.POST('/api/auth/invite/accept', {
      body: {
        token,
        password: String(form.get('password') ?? ''),
        password_again: String(form.get('password_again') ?? ''),
      },
    })
    if (error) {
      const messages = (error as { messages?: string[] }).messages ?? []
      setError([errorMessage(t, error), ...messages].join(' '))
      return
    }
    window.history.replaceState(null, '', '/') // Remove the used token from the address bar.
    onSignedIn()
  }

  if (info === null) return <p>{t('invite.checking')}</p>
  if (info === 'invalid') {
    return (
      <p role="alert" className="error">
        {t('invite.invalid')}
      </p>
    )
  }
  return (
    <form className="card" onSubmit={submit} aria-label={t('invite.title')}>
      <h1>{t('invite.title')}</h1>
      <p>
        {info.purpose === 'reset'
          ? t('invite.resetWelcome', { name: info.username })
          : t('invite.welcome', { name: info.username })}
      </p>
      <input type="text" name="username" value={info.username} autoComplete="username" readOnly hidden />
      <label>
        {t('invite.password')}
        <input name="password" type="password" autoComplete="new-password" required minLength={8} />
      </label>
      <label>
        {t('invite.again')}
        <input name="password_again" type="password" autoComplete="new-password" required minLength={8} />
      </label>
      <p className="muted">{t('invite.rules')}</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button type="submit">{t('invite.submit')}</button>
    </form>
  )
}
