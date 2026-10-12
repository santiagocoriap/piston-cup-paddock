import { useEffect, useState, type FormEvent, type SyntheticEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Report = components['schemas']['ReportOut']

/** The AI race report. The AI writes only the text. The facts come from the app. */
export function ReportSection({ roundId, adminView }: { roundId: number; adminView: boolean }) {
  const { t } = useTranslation()
  const reports = useLoad(
    () => api.GET('/api/rounds/{round_id}/reports', { params: { path: { round_id: roundId } } }),
    [roundId],
  )
  const data = reports.data
  const pending = data?.reports.some((r) => r.status === 'pending') ?? false
  const { reload } = reports

  // The worker writes the text. Check again until it is done.
  useEffect(() => {
    if (!pending) return
    const timer = window.setTimeout(reload, 5000)
    return () => window.clearTimeout(timer)
  }, [pending, reload, data])

  if (!data) return null
  const ready = data.reports.filter((r) => r.status === 'ready')
  const [latest, ...older] = ready
  return (
    <section aria-label={t('report.title')}>
      <h2>{t('report.title')}</h2>
      {latest ? <ReportText report={latest} open /> : <p className="muted">{t('report.none')}</p>}
      {older.length > 0 && (
        <details>
          <summary>{t('report.older', { count: older.length })}</summary>
          {older.map((report) => (
            <ReportText key={report.id} report={report} />
          ))}
        </details>
      )}
      {adminView && data.can_generate && (
        <ReportAdmin roundId={roundId} reports={data.reports} aiConfigured={data.ai_configured} onChange={reload} />
      )}
    </section>
  )
}

function ReportText({ report, open = false }: { report: Report; open?: boolean }) {
  const { t, i18n } = useTranslation()
  const [unread, setUnread] = useState(report.unread)
  // An unread report starts closed. Opening it marks it as read.
  const [startOpen] = useState(open && !report.unread)

  async function markRead(event: SyntheticEvent<HTMLDetailsElement>) {
    if (!event.currentTarget.open || !unread) return
    const { error } = await api.POST('/api/reports/{report_id}/read', {
      params: { path: { report_id: report.id } },
    })
    if (!error) setUnread(false)
  }

  return (
    <details className="card report" open={startOpen} onToggle={markRead}>
      <summary>
        {t('report.version', { number: report.number })}
        {unread && <span className="badge">{t('report.new')}</span>}
      </summary>
      <p className="muted">
        {t('report.meta', {
          status: report.result_status ? t(`review.status.${report.result_status}`) : '—',
          version: report.source_version ?? '—',
          date: formatDateTime(report.generated_at, i18n.language),
          language: t(`report.languages.${report.language}`),
        })}
      </p>
      {report.text.split(/\n\s*\n/).map((paragraph, index) => (
        <p key={index}>{paragraph}</p>
      ))}
      <p className="muted">{t('report.aiNote')}</p>
    </details>
  )
}

function ReportAdmin({
  roundId,
  reports,
  aiConfigured,
  onChange,
}: {
  roundId: number
  reports: Report[]
  aiConfigured: boolean
  onChange: () => void
}) {
  const { t, i18n } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const [language, setLanguage] = useState<'es' | 'en'>(i18n.language === 'en' ? 'en' : 'es')
  const [tone, setTone] = useState<'friendly' | 'roast'>('friendly')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    const { error } = await api.POST('/api/rounds/{round_id}/reports', {
      params: { path: { round_id: roundId } },
      body: { language, tone },
    })
    if (error) setError(errorMessage(t, error))
    else onChange()
  }

  return (
    <div className="card">
      <h3>{t('report.generate')}</h3>
      {!aiConfigured && <p className="warning">{t('report.notConfigured')}</p>}
      <form className="inline" onSubmit={submit} aria-label={t('report.generate')}>
        <label>
          {t('report.language')}
          <select value={language} onChange={(e) => setLanguage(e.target.value as 'es' | 'en')}>
            <option value="es">{t('report.languages.es')}</option>
            <option value="en">{t('report.languages.en')}</option>
          </select>
        </label>
        <label>
          {t('report.tone')}
          <select value={tone} onChange={(e) => setTone(e.target.value as 'friendly' | 'roast')}>
            <option value="friendly">{t('report.tones.friendly')}</option>
            <option value="roast">{t('report.tones.roast')}</option>
          </select>
        </label>
        <button type="submit">{t('report.generateButton')}</button>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {reports.length > 0 && (
        <ul className="list">
          {reports.map((report) => (
            <li key={report.id}>
              {t('report.version', { number: report.number })} · {t(`report.status.${report.status}`)} ·{' '}
              {report.model} · {report.prompt_version}
              {report.error && <span className="error"> · {report.error}</span>}
              {report.facts && (
                <details>
                  <summary>{t('report.facts')}</summary>
                  <pre className="mono">{JSON.stringify(report.facts, null, 1)}</pre>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
