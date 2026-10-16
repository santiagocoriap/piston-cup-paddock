import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { errorMessage } from '../lib/errors'
import { Avatar } from '../components/Avatar'
import { Icon } from '../components/Icon'
import { PasswordField } from '../components/PasswordField'

/** The page of a one-time link. The token is after "#", so the server logs never see it. */
export function InvitePage({ onSignedIn }: { onSignedIn: () => void }) {
  const { t } = useTranslation()
  const [token] = useState(() => window.location.hash.slice(1))
  const [info, setInfo] = useState<{ username: string; purpose: string } | null | 'invalid'>(null)
  const [error, setError] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.POST('/api/auth/invite/check', { body: { token } }).then(({ data }) => {
      setInfo(data ?? 'invalid')
    })
  }, [token])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const form = new FormData(event.currentTarget)
    setBusy(true)
    await api.GET('/api/auth/csrf')
    const { error } = await api.POST('/api/auth/invite/accept', {
      body: {
        token,
        password: String(form.get('password') ?? ''),
        password_again: String(form.get('password_again') ?? ''),
      },
    })
    setBusy(false)
    if (error) {
      const messages = (error as { messages?: string[] }).messages ?? []
      setError([errorMessage(t, error), ...messages].join(' '))
      return
    }
    window.history.replaceState(null, '', '/') // Remove the used token from the address bar.
    onSignedIn()
  }

  if (info === null) {
    return (
      <p className="auth-checking" role="status">
        <span className="spinner" aria-hidden="true" />
        {t('invite.checking')}
      </p>
    )
  }
  if (info === 'invalid') {
    return (
      <div className="auth-form invite-invalid">
        <span className="invite-invalid-icon" aria-hidden="true">
          <Icon name="ban" />
        </span>
        <h1>{t('invite.invalidTitle')}</h1>
        <p role="alert" className="muted">
          {t('invite.invalid')}
        </p>
        <a className="button-link auth-submit" href="/">
          {t('invite.toLogin')}
        </a>
      </div>
    )
  }
  const checks = [
    { key: 'length', ok: password.length >= 8 },
    { key: 'notDigits', ok: password.length > 0 && !/^\d+$/.test(password) },
    { key: 'match', ok: password.length > 0 && password === again },
  ]
  const passed = checks.filter((check) => check.ok).length
  const reset = info.purpose === 'reset'
  return (
    <form className="auth-form" onSubmit={submit} aria-label={t('invite.title')}>
      <header className="invite-head">
        <Avatar name={info.username} className="invite-avatar" />
        <div>
          <span className="badge invite-badge">
            <Icon name={reset ? 'rotate' : 'user'} small />
            {reset ? t('invite.badgeReset') : t('invite.badgeInvite')}
          </span>
          <h1>{t('invite.title')}</h1>
        </div>
      </header>
      <p className="muted invite-welcome">
        {reset ? t('invite.resetWelcome', { name: info.username }) : t('invite.welcome', { name: info.username })}
      </p>
      <input type="text" name="username" value={info.username} autoComplete="username" readOnly hidden />
      <PasswordField
        label={t('invite.password')}
        name="password"
        autoComplete="new-password"
        required
        minLength={8}
        onChange={(event) => setPassword(event.target.value)}
      />
      <PasswordField
        label={t('invite.again')}
        name="password_again"
        autoComplete="new-password"
        required
        minLength={8}
        onChange={(event) => setAgain(event.target.value)}
      />
      <div className="password-checks">
        <div
          className={`strength strength-${passed}`}
          role="meter"
          aria-label={t('invite.rulesTitle')}
          aria-valuemin={0}
          aria-valuemax={checks.length}
          aria-valuenow={passed}
        >
          {checks.map((check) => (
            <span key={check.key} className={check.ok ? 'on' : undefined} />
          ))}
        </div>
        <ul aria-label={t('invite.rulesTitle')}>
          {checks.map((check) => (
            <li key={check.key} className={check.ok ? 'ok' : undefined}>
              <Icon name={check.ok ? 'check' : 'close'} small />
              {t(`invite.checks.${check.key}`)}
            </li>
          ))}
        </ul>
      </div>
      {error && (
        <p role="alert" className="auth-error">
          <Icon name="alert" small />
          {error}
        </p>
      )}
      <button type="submit" className="auth-submit" disabled={busy || passed < checks.length}>
        {busy && <span className="spinner" aria-hidden="true" />}
        {t('invite.submit')}
      </button>
    </form>
  )
}
