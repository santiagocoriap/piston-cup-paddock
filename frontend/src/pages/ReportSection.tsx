import { useEffect, useState, type FormEvent, type SyntheticEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Report = components['schemas']['ReportOut']
type Tone = 'sarcastic' | 'friendly' | 'roast'
/** A race report belongs to a round. A season report belongs to a season. */
type Target = { kind: 'round' | 'season'; id: number }

function loadReports(target: Target) {
  return target.kind === 'round'
    ? api.GET('/api/rounds/{round_id}/reports', { params: { path: { round_id: target.id } } })
    : api.GET('/api/seasons/{season_id}/reports', { params: { path: { season_id: target.id } } })
}

function createReport(target: Target, body: { language: 'es' | 'en'; tone: Tone }) {
  return target.kind === 'round'
    ? api.POST('/api/rounds/{round_id}/reports', { params: { path: { round_id: target.id } }, body })
    : api.POST('/api/seasons/{season_id}/reports', { params: { path: { season_id: target.id } }, body })
}

/** The AI race report or season report. The AI writes only the text. The facts come from the app. */
export function ReportSection({ target, adminView }: { target: Target; adminView: boolean }) {
  const { t } = useTranslation()
  const prefix = target.kind === 'round' ? 'report' : 'seasonReport'
  const reports = useLoad(() => loadReports(target), [target.kind, target.id])
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
    <section aria-label={t(`${prefix}.title`)}>
      <h2>{t(`${prefix}.title`)}</h2>
      {latest ? <ReportText report={latest} open target={target.kind} /> : <p className="muted">{t('report.none')}</p>}
      {older.length > 0 && (
        <details>
          <summary>{t('report.older', { count: older.length })}</summary>
          {older.map((report) => (
            <ReportText key={report.id} report={report} target={target.kind} />
          ))}
        </details>
      )}
      {adminView && data.can_generate && (
        <ReportAdmin target={target} reports={data.reports} aiConfigured={data.ai_configured} onChange={reload} />
      )}
    </section>
  )
}

function ReportText({ report, open = false, target = 'round' }: { report: Report; open?: boolean; target?: Target['kind'] }) {
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
        {target === 'season'
          ? t('seasonReport.meta', {
              status: t(`seasonReport.status.${report.result_status}`),
              date: formatDateTime(report.generated_at, i18n.language),
              language: t(`report.languages.${report.language}`),
            })
          : t('report.meta', {
              status: report.result_status ? t(`review.status.${report.result_status}`) : '—',
              version: report.source_version ?? '—',
              date: formatDateTime(report.generated_at, i18n.language),
              language: t(`report.languages.${report.language}`),
            })}
      </p>
      {report.text
        .split(/\n+/)
        .filter((line) => line.trim())
        .map((paragraph, index) => (
        <p key={index}>{paragraph}</p>
      ))}
      <p className="muted">{t('report.aiNote')}</p>
    </details>
  )
}

function ReportAdmin({
  target,
  reports,
  aiConfigured,
  onChange,
}: {
  target: Target
  reports: Report[]
  aiConfigured: boolean
  onChange: () => void
}) {
  const { t, i18n } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const [language, setLanguage] = useState<'es' | 'en'>(i18n.language === 'en' ? 'en' : 'es')
  const [tone, setTone] = useState<Tone>('sarcastic')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    const { error } = await createReport(target, { language, tone })
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
          <select value={tone} onChange={(e) => setTone(e.target.value as Tone)}>
            <option value="sarcastic">{t('report.tones.sarcastic')}</option>
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
