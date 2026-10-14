import { useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { api, readCookie } from '../api/client'
import type { components } from '../api/schema'
import { Avatar } from '../components/Avatar'
import { Icon } from '../components/Icon'
import { Feedback, SettingsRow, type Message } from '../components/SettingsRow'
import { errorMessage } from '../lib/errors'
import { useMe, useUpdateMe } from '../session'
import { TelemetryCard } from './TelemetryCard'
import { CalendarFeedCard } from './CalendarFeedCard'
import { Breadcrumbs } from '../components/Breadcrumbs'

type Me = components['schemas']['Me']

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

// The browser makes the picture a square of this size before the upload.
const AVATAR_SIZE = 256

function allZones(): string[] {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] }
  try {
    return intl.supportedValuesOf?.('timeZone') ?? COMMON_ZONES
  } catch {
    return COMMON_ZONES
  }
}

/** The account of the signed-in user: the picture, the language and timezone, the phone
 * calendar, the telemetry, and the password. */
export function AccountPage() {
  const { t } = useTranslation()
  const me = useMe()
  const role = me.is_admin ? t('nav.roleLeagueAdmin') : me.can_manage ? t('nav.roleAdmin') : t('nav.roleDriver')

  return (
    <section className="account-page">
      <Breadcrumbs items={[{ label: t('nav.account') }]} />
      <header className="account-hero">
        <AvatarPicker me={me}>
          <p className="eyebrow">{t('account.title')}</p>
          <h1>{me.username}</h1>
          <p className="muted">{role}</p>
        </AvatarPicker>
      </header>
      <PreferencesForm />
      <CalendarFeedCard />
      <TelemetryCard />
      <PasswordForm />
    </section>
  )
}

/** Make the chosen picture a square from its center, and make it small. */
async function squareJpeg(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file)
  const side = Math.min(bitmap.width, bitmap.height)
  const canvas = document.createElement('canvas')
  canvas.width = AVATAR_SIZE
  canvas.height = AVATAR_SIZE
  canvas
    .getContext('2d')!
    .drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, AVATAR_SIZE, AVATAR_SIZE)
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('image'))), 'image/jpeg', 0.9),
  )
}

function AvatarPicker({ me, children }: { me: Me; children: ReactNode }) {
  const { t } = useTranslation()
  const updateMe = useUpdateMe()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<Message>(null)

  async function send(method: 'POST' | 'DELETE', body?: FormData) {
    setBusy(true)
    setMessage(null)
    const response = await fetch('/api/auth/me/avatar', {
      method,
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': readCookie('csrftoken') ?? '' },
      body,
    })
    setBusy(false)
    if (response.ok) {
      updateMe(await response.json())
      setMessage({ kind: 'saved', text: t(method === 'POST' ? 'account.photoSaved' : 'account.photoRemoved') })
    } else {
      const problem = await response.json().catch(() => null)
      setMessage({ kind: 'error', text: errorMessage(t, problem ?? { detail: 'generic' }) })
    }
  }

  async function choose(file: File | undefined) {
    if (input.current) input.current.value = ''
    if (!file) return
    let picture: Blob
    try {
      picture = await squareJpeg(file)
    } catch {
      setMessage({ kind: 'error', text: t('errors.image_not_supported') })
      return
    }
    const form = new FormData()
    form.append('file', picture, 'avatar.jpg')
    await send('POST', form)
  }

  return (
    <>
      <button
        type="button"
        className="avatar-button"
        onClick={() => input.current?.click()}
        disabled={busy}
        aria-label={me.avatar_url ? t('account.changePhoto') : t('account.addPhoto')}
      >
        <Avatar name={me.username} url={me.avatar_url} className="account-avatar" />
        <span className="avatar-edit" aria-hidden="true">
          <Icon name="upload" small />
        </span>
      </button>
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        onChange={(event) => choose(event.target.files?.[0])}
      />
      <div className="account-who">
        {children}
        <div className="avatar-actions">
        <button type="button" className="secondary" onClick={() => input.current?.click()} disabled={busy}>
          {me.avatar_url ? t('account.changePhoto') : t('account.addPhoto')}
        </button>
        {me.avatar_url && (
          <button type="button" className="link" onClick={() => send('DELETE')} disabled={busy}>
            {t('account.removePhoto')}
          </button>
        )}
      </div>
        <p className="muted avatar-help">{t('account.photoHelp')}</p>
        <Feedback message={message} />
      </div>
    </>
  )
}

function PreferencesForm() {
  const { t, i18n } = useTranslation()
  const me = useMe()
  const updateMe = useUpdateMe()
  const [message, setMessage] = useState<Message>(null)
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
    <SettingsRow id="preferences" title={t('account.preferences')} help={t('account.timezoneHelp')}>
      <form onSubmit={submit} aria-label={t('account.preferences')}>
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
        <Feedback message={message} />
        <div className="settings-actions">
          <button type="submit">{t('common.save')}</button>
        </div>
      </form>
    </SettingsRow>
  )
}

function PasswordForm() {
  const { t } = useTranslation()
  const [message, setMessage] = useState<Message>(null)

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
    <SettingsRow id="password" title={t('password.title')} help={t('password.help')}>
      <form onSubmit={submit} aria-label={t('password.title')}>
        <label>
          {t('password.current')}
          <input name="current" type="password" autoComplete="current-password" required />
        </label>
        <div className="settings-pair">
          <label>
            {t('password.new')}
            <input name="new" type="password" autoComplete="new-password" required minLength={8} />
          </label>
          <label>
            {t('password.again')}
            <input name="new_again" type="password" autoComplete="new-password" required minLength={8} />
          </label>
        </div>
        <Feedback message={message} />
        <div className="settings-actions">
          <button type="submit">{t('password.save')}</button>
        </div>
      </form>
    </SettingsRow>
  )
}
