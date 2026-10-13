import { useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { errorMessage } from '../lib/errors'
import { useMe, useUpdateMe } from '../session'
import { TelemetryCard } from './TelemetryCard'
import { CalendarFeedCard } from './CalendarFeedCard'

const COMMON_ZONES = [
  'America/Argentina/Buenos_Aires',
  'America/Montevideo',
  'America/Santiago',
  'America/Sao_Paulo',
  'America/Mexico_City',
  'America/New_York',
  'Europe/Madrid',
  'Europe/London',
  'UTC',
]

function allZones(): string[] {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] }
  try {
    return intl.supportedValuesOf?.('timeZone') ?? COMMON_ZONES
  } catch {
    return COMMON_ZONES
  }
}

/** The language and the timezone of the signed-in user. */
export function AccountPage() {
  const { t, i18n } = useTranslation()
  const me = useMe()
  const updateMe = useUpdateMe()
  const [message, setMessage] = useState<{ kind: 'error' | 'saved'; text: string } | null>(null)
  const zones = useMemo(() => allZones(), [])
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage(null)
    const form = new FormData(event.currentTarget)
    const { data, error } = await api.PATCH('/api/auth/me', {
      body: {
        language: form.get('language') as 'es' | 'en',
        timezone: String(form.get('timezone') ?? ''),
      },
    })
    if (error || !data) {
      setMessage({ kind: 'error', text: errorMessage(t, error) })
      return
    }
    await i18n.changeLanguage(data.language)
    updateMe(data)
    setMessage({ kind: 'saved', text: i18n.t('account.saved') }) // The new language.
  }

  return (
    <section className="narrow-section">
      <h1>{t('account.title')}</h1>
      <form className="card" onSubmit={submit} aria-label={t('account.title')}>
        <label>
          {t('account.language')}
          <select name="language" defaultValue={me.language}>
            <option value="es">Español</option>
            <option value="en">English</option>
          </select>
        </label>
        <label>
          {t('account.timezone')}
          <select name="timezone" defaultValue={me.timezone}>
            <option value="">{t('account.browserZone', { zone: browserZone })}</option>
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone.replaceAll('_', ' ')}
              </option>
            ))}
          </select>
        </label>
        <p className="muted">{t('account.timezoneHelp')}</p>
        {message && (
          <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'success'}>
            {message.text}
          </p>
        )}
        <button type="submit">{t('common.save')}</button>
      </form>
      <CalendarFeedCard />
      <TelemetryCard />
      <PasswordForm />
    </section>
  )
}

function PasswordForm() {
  const { t } = useTranslation()
  const [message, setMessage] = useState<{ kind: 'error' | 'saved'; text: string } | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage(null)
    const element = event.currentTarget
    const form = new FormData(element)
    const { error } = await api.POST('/api/auth/password', {
      body: {
        current: String(form.get('current') ?? ''),
        new: String(form.get('new') ?? ''),
        new_again: String(form.get('new_again') ?? ''),
      },
    })
    if (error) {
      const messages = (error as { messages?: string[] }).messages ?? []
      setMessage({ kind: 'error', text: [errorMessage(t, error), ...messages].join(' ') })
      return
    }
    element.reset()
    setMessage({ kind: 'saved', text: t('password.saved') })
  }

  return (
    <form className="card" onSubmit={submit} aria-label={t('password.title')}>
      <h2>{t('password.title')}</h2>
      <label>
        {t('password.current')}
        <input name="current" type="password" autoComplete="current-password" required />
      </label>
      <label>
        {t('password.new')}
        <input name="new" type="password" autoComplete="new-password" required minLength={8} />
      </label>
      <label>
        {t('password.again')}
        <input name="new_again" type="password" autoComplete="new-password" required minLength={8} />
      </label>
      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'success'}>
          {message.text}
        </p>
      )}
      <button type="submit">{t('common.save')}</button>
    </form>
  )
}
