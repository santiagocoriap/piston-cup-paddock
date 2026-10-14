import { useEffect, useState, type FormEvent, type SyntheticEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { api } from '../api/client'
import { AdminActions } from '../components/AdminActions'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Report = components['schemas']['ReportOut']
type Tone = 'sarcastic' | 'friendly' | 'roast'
/** A race report belongs to a round. A season report belongs to a season. */
type Target = { kind: 'round' | 'season'; id: number }
/** The top of the article: a picture, a small line above the title, and the title. */
type Masthead = { cover?: string | null; kicker?: string; headline?: string }

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
export function ReportSection({
  target,
  adminView,
  masthead = {},
}: {
  target: Target
  adminView: boolean
  masthead?: Masthead
}) {
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

  async function regenerate(id: number) {
    const { error } = await api.POST('/api/reports/{report_id}/regenerate', { params: { path: { report_id: id } } })
    if (!error) reload()
  }
  return (
    <section aria-label={t(`${prefix}.title`)}>
      <div className="section-head">
        <h2>{t(`${prefix}.title`)}</h2>
        {adminView && data.can_generate && (
          <AdminActions
            actions={[
              {
                id: 'generate',
                label: t('report.generate'),
                content: () => (
                  <ReportAdmin target={target} reports={data.reports} aiConfigured={data.ai_configured} onChange={reload} />
                ),
              },
            ]}
          />
        )}
      </div>
      {latest?.outdated && (
        <p className="warning" role="status">
          {t('report.outdated')}{' '}
          {adminView && data.can_generate && (
            <button type="button" className="link-button" onClick={() => regenerate(latest.id)}>
              {t('report.regenerate')}
            </button>
          )}
        </p>
      )}
      {latest ? (
        <ReportArticle key={latest.id} report={latest} target={target.kind} masthead={masthead} />
      ) : (
        <p className="muted">{t('report.none')}</p>
      )}
      {older.length > 0 && (
        <details>
          <summary>{t('report.older', { count: older.length })}</summary>
          {older.map((report) => (
            <ReportText key={report.id} report={report} target={target.kind} />
          ))}
        </details>
      )}
    </section>
  )
}

function paragraphs(text: string) {
  return text.split(/\n+/).filter((line) => line.trim())
}

function metaLine(t: TFunction, language: string, report: Report, target: Target['kind']) {
  return target === 'season'
    ? t('seasonReport.meta', {
        status: t(`seasonReport.status.${report.result_status}`),
        date: formatDateTime(report.generated_at, language),
        language: t(`report.languages.${report.language}`),
      })
    : t('report.meta', {
        status: report.result_status ? t(`review.status.${report.result_status}`) : '—',
        version: report.source_version ?? '—',
        date: formatDateTime(report.generated_at, language),
        language: t(`report.languages.${report.language}`),
      })
}

/** The newest report as a news article: a picture, a title, a byline, and the text in a
 * column for reading. An unread report shows only the first paragraph. The button
 * opens the rest and marks the report as read. */
function ReportArticle({ report, target, masthead }: { report: Report; target: Target['kind']; masthead: Masthead }) {
  const { t, i18n } = useTranslation()
  const [unread, setUnread] = useState(report.unread)
  const [expanded, setExpanded] = useState(!report.unread)
  const [lede, ...rest] = paragraphs(report.text)
  const prefix = target === 'round' ? 'report' : 'seasonReport'

  async function readAll() {
    setExpanded(true)
    if (!unread) return
    const { error } = await api.POST('/api/reports/{report_id}/read', { params: { path: { report_id: report.id } } })
    if (!error) setUnread(false)
  }

  return (
    <article
      className={masthead.cover ? 'news has-cover' : 'news'}
      aria-label={masthead.headline ?? t(`${prefix}.title`)}
    >
      {masthead.cover && (
        <div className="news-cover">
          <img src={masthead.cover} alt="" />
        </div>
      )}
      <header className="news-head">
        <p className="news-kicker">
          {masthead.kicker ?? t(`${prefix}.title`)}
          {unread && <span className="badge">{t('report.new')}</span>}
        </p>
        {masthead.headline && (
          <h3 id={`news-${report.id}`} className="news-title">
            {masthead.headline}
          </h3>
        )}
        <p className="news-byline">
          <span>{t('report.byline')}</span>
          <span>
            {t('report.version', { number: report.number })} · {metaLine(t, i18n.language, report, target)}
          </span>
        </p>
      </header>
      <div className="news-body">
        {lede && <p className="news-lede">{lede}</p>}
        {expanded ? (
          <>
            {rest.map((paragraph, index) => (
              <p key={index}>{paragraph}</p>
            ))}
            <p className="news-note">{t('report.aiNote')}</p>
          </>
        ) : (
          rest.length > 0 && (
            <button type="button" className="news-more" onClick={readAll}>
              {t('report.readAll')}
            </button>
          )
        )}
      </div>
    </article>
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
      <p className="muted">{metaLine(t, i18n.language, report, target)}</p>
      {paragraphs(report.text).map((paragraph, index) => (
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
