import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { Loading } from '../components/Layout'
import { formatDateTime, formatLapTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { useMode } from '../session'

type Board = components['schemas']['BoardOut']
type RecordLap = components['schemas']['RecordLapOut']

export function RecordsPage() {
  const { t } = useTranslation()
  const [layoutId, setLayoutId] = useState('')
  const records = useLoad(
    () => api.GET('/api/records', { params: { query: layoutId ? { layout_id: Number(layoutId) } : {} } }),
    [layoutId],
  )

  return (
    <section>
      <h1>{t('records.title')}</h1>
      <p className="muted">{t('records.help')}</p>
      <p className="exports">
        <a href="/api/records/export.csv" download>
          {t('exports.records')}
        </a>
      </p>
      {!records.data ? (
        <Loading failed={records.failed} />
      ) : (
        <>
          {records.data.layouts.length > 0 && (
            <label className="inline-filter">
              {t('records.layout')}
              <select value={layoutId} onChange={(event) => setLayoutId(event.target.value)}>
                <option value="">{t('records.all')}</option>
                {records.data.layouts.map((layout) => (
                  <option key={layout.id} value={layout.id}>
                    {layout.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {records.data.boards.length === 0 && <p>{t('records.empty')}</p>}
          <div className="boards">
            {records.data.boards.map((board) => (
              <BoardCard key={`${board.layout_id}-${board.car_id}-${board.category}`} board={board} onChange={records.reload} />
            ))}
          </div>
        </>
      )}
    </section>
  )
}

function BoardCard({ board, onChange }: { board: Board; onChange: () => void }) {
  const { t, i18n } = useTranslation()
  const { mode } = useMode()
  const title = `${t(`records.category.${board.category}`)}: ${board.track_name} · ${board.layout_name} · ${board.car_name}`
  return (
    <article className="card board" aria-label={title}>
      <h2 className="board-title">{title}</h2>
      {board.record_ms ? (
        <p className="record-time">
          {formatLapTime(board.record_ms)}
          {board.holders.length > 1 && <span className="badge">{t('records.shared')}</span>}
        </p>
      ) : (
        <p className="muted">—</p>
      )}
      {board.holders.map((holder) => (
        <LapDetails key={holder.lap_id} lap={holder} />
      ))}

      <details>
        <summary>{t('records.history')}</summary>
        <ol className="record-history">
          {board.history.map((item) => (
            <li key={`${item.kind}-${item.lap.lap_id}`} className={`history-${item.kind}`}>
              <strong>{formatLapTime(item.lap.lap_time_ms)}</strong> · {item.lap.driver_name} ·{' '}
              {formatDateTime(item.lap.date, i18n.language)} · {t(`records.kind.${item.kind}`)}
              {item.lap.ineligible_reason && ` (${t(`records.reason.${item.lap.ineligible_reason}`)})`}
              {mode === 'admin' && item.lap.can_invalidate && item.kind !== 'removed' && (
                <ActionForm
                  title={`${t('records.invalidate')} ${formatLapTime(item.lap.lap_time_ms)}`}
                  submitLabel={t('records.invalidate')}
                  onSubmit={async (form) => {
                    const { error } = await api.POST('/api/laps/{lap_id}/invalidate', {
                      params: { path: { lap_id: item.lap.lap_id } },
                      body: { reason: String(form.get('reason') ?? '') },
                    })
                    if (!error) onChange()
                    return error
                  }}
                >
                  <label>
                    {t('records.invalidateReason')}
                    <input name="reason" required maxLength={500} />
                  </label>
                </ActionForm>
              )}
            </li>
          ))}
        </ol>
      </details>
    </article>
  )
}

function LapDetails({ lap }: { lap: RecordLap }) {
  const { t, i18n } = useTranslation()
  return (
    <dl className="lap-details">
      <dt>{t('records.holder')}</dt>
      <dd>{lap.driver_name}</dd>
      <dt>{t('records.date')}</dt>
      <dd>
        {formatDateTime(lap.date, i18n.language)} ·{' '}
        <Link to={`/rounds/${lap.round_id}`}>
          {t('records.round', { number: lap.round_number, season: lap.season_name })}
        </Link>
      </dd>
      <dt>{t('records.conditions')}</dt>
      <dd>{lap.conditions ?? t('records.unknown')}</dd>
      <dt>{t('records.handicap')}</dt>
      <dd>
        {lap.ballast_kg} kg / {lap.restrictor} %
      </dd>
      <dt>{t('records.tyre')}</dt>
      <dd>{lap.tyre || '—'}</dd>
      {lap.sectors_ms.length > 0 && (
        <>
          <dt>{t('records.sectors')}</dt>
          <dd className="mono">{lap.sectors_ms.map((s) => formatLapTime(s)).join(' · ')}</dd>
        </>
      )}
      <dt>{t('records.source')}</dt>
      <dd className="muted">{t('records.sourceText', { file: lap.source_file, user: lap.uploaded_by ?? '—' })}</dd>
    </dl>
  )
}
