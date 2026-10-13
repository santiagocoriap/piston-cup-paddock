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
type Filters = { layout: string; car: string; category: string; season: string; overall: boolean }

const NO_FILTERS: Filters = { layout: '', car: '', category: '', season: '', overall: false }

export function RecordsPage() {
  const { t } = useTranslation()
  const { mode } = useMode()
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const records = useLoad(
    () =>
      api.GET('/api/records', {
        params: {
          query: {
            ...(filters.layout ? { layout_id: Number(filters.layout) } : {}),
            ...(filters.car && !filters.overall ? { car_id: Number(filters.car) } : {}),
            ...(filters.category ? { category: filters.category as 'race' | 'qualifying' } : {}),
            ...(filters.season ? { season_id: Number(filters.season) } : {}),
            ...(filters.overall ? { overall: true } : {}),
          },
        },
      }),
    [filters.layout, filters.car, filters.category, filters.season, filters.overall],
  )
  const set = (name: keyof Filters, value: string | boolean) => setFilters((old) => ({ ...old, [name]: value }))

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
          <div className="forms" role="group" aria-label={t('records.filters')}>
            <label className="inline-filter">
              {t('records.layout')}
              <select value={filters.layout} onChange={(e) => set('layout', e.target.value)}>
                <option value="">{t('records.all')}</option>
                {records.data.layouts.map((layout) => (
                  <option key={layout.id} value={layout.id}>
                    {layout.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="inline-filter">
              {t('records.car')}
              <select value={filters.car} disabled={filters.overall} onChange={(e) => set('car', e.target.value)}>
                <option value="">{t('records.allCars')}</option>
                {records.data.cars.map((car) => (
                  <option key={car.id} value={car.id}>
                    {car.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="inline-filter">
              {t('records.session')}
              <select value={filters.category} onChange={(e) => set('category', e.target.value)}>
                <option value="">{t('records.allSessions')}</option>
                <option value="qualifying">{t('records.category.qualifying')}</option>
                <option value="race">{t('records.category.race')}</option>
              </select>
            </label>
            <label className="inline-filter">
              {t('records.season')}
              <select value={filters.season} onChange={(e) => set('season', e.target.value)}>
                <option value="">{t('records.allTime')}</option>
                {records.data.seasons.map((season) => (
                  <option key={season.id} value={season.id}>
                    {season.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={filters.overall} onChange={(e) => set('overall', e.target.checked)} />
              {t('records.overall')}
            </label>
          </div>
          {records.data.boards.length === 0 && <p>{t('records.empty')}</p>}
          <div className="boards">
            {records.data.boards.map((board) => (
              <BoardCard key={`${board.layout_id}-${board.car_id}-${board.category}`} board={board} onChange={records.reload} />
            ))}
          </div>
          {mode === 'admin' && <ManualRecordForm onSaved={records.reload} />}
        </>
      )}
    </section>
  )
}

function BoardCard({ board, onChange }: { board: Board; onChange: () => void }) {
  const { t, i18n } = useTranslation()
  const { mode } = useMode()
  const car = board.car_id ? board.car_name : t('records.allCars')
  const title = `${t(`records.category.${board.category}`)}: ${board.track_name} · ${board.layout_name} · ${car}`
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
        <LapDetails key={holder.lap_id} lap={holder} onChange={onChange} />
      ))}

      <details>
        <summary>{t('records.history')}</summary>
        <ol className="record-history">
          {board.history.map((item) => (
            <li key={`${item.kind}-${item.lap.lap_id}`} className={`history-${item.kind}`}>
              <strong>{formatLapTime(item.lap.lap_time_ms)}</strong> · {item.lap.driver_name} ·{' '}
              {formatDateTime(item.lap.date, i18n.language)} · {t(`records.kind.${item.kind}`)}
              {item.lap.manual && ` · ${t(item.lap.verified ? 'records.verified' : 'records.unverified')}`}
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

function conditionsText(t: (key: string) => string, conditions: Record<string, unknown>): string {
  const parts = [
    conditions.weather,
    conditions.time_of_day,
    conditions.air_temp_c !== null && conditions.air_temp_c !== undefined ? `${conditions.air_temp_c} °C ${t('records.air')}` : null,
    conditions.track_temp_c !== null && conditions.track_temp_c !== undefined ? `${conditions.track_temp_c} °C ${t('records.track')}` : null,
    conditions.grip,
  ].filter((part) => part !== null && part !== undefined && part !== '')
  return parts.length > 0 ? parts.join(' · ') : t('records.unknown')
}

function LapDetails({ lap, onChange }: { lap: RecordLap; onChange: () => void }) {
  const { t, i18n } = useTranslation()
  const { mode } = useMode()
  if (lap.manual) {
    return (
      <dl className="lap-details">
        <dt>{t('records.holder')}</dt>
        <dd>
          {lap.driver_name}{' '}
          <span className="badge">{t(lap.verified ? 'records.verified' : 'records.unverified')}</span>
        </dd>
        <dt>{t('records.date')}</dt>
        <dd>{formatDateTime(lap.date, i18n.language)}</dd>
        <dt>{t('records.source')}</dt>
        <dd className="muted">{t('records.manualSource', { source: lap.source_file })}</dd>
        {mode === 'admin' && lap.manual_id && (
          <dd>
            {lap.can_verify && (
              <button
                type="button"
                className="secondary small"
                onClick={async () => {
                  await api.POST('/api/records/manual/{record_id}/verify', { params: { path: { record_id: lap.manual_id! } } })
                  onChange()
                }}
              >
                {t('records.verify')}
              </button>
            )}{' '}
            <button
              type="button"
              className="secondary small"
              onClick={async () => {
                if (!window.confirm(t('records.confirmRemove'))) return
                await api.DELETE('/api/records/manual/{record_id}', { params: { path: { record_id: lap.manual_id! } } })
                onChange()
              }}
            >
              {t('records.remove')}
            </button>
          </dd>
        )}
      </dl>
    )
  }
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
      <dd>{conditionsText(t, lap.conditions)}</dd>
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

/** An admin adds a historical record with a source. It stays unverified until checked. */
function ManualRecordForm({ onSaved }: { onSaved: () => void }) {
  const { t } = useTranslation()
  const championships = useLoad(() => api.GET('/api/championships'), [])
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  const managed = championships.data?.filter((c) => c.can_manage) ?? []
  if (managed.length === 0) return null
  return (
    <div className="forms">
      <ActionForm
        title={t('records.addManual')}
        submitLabel={t('common.create')}
        onSubmit={async (form) => {
          const [minutes, seconds] = String(form.get('time')).split(':')
          const ms = Math.round((Number(minutes) * 60 + Number(seconds)) * 1000)
          const { error } = await api.POST('/api/records/manual', {
            body: {
              championship_id: Number(form.get('championship_id')),
              layout_id: Number(form.get('layout_id')),
              car_id: Number(form.get('car_id')),
              category: form.get('category') as 'race' | 'qualifying',
              lap_time_ms: ms,
              driver_name: String(form.get('driver_name')),
              date: String(form.get('date')),
              source: String(form.get('source')),
            },
          })
          if (!error) onSaved()
          return error
        }}
      >
        <label>
          {t('records.championship')}
          <select name="championship_id" required>
            {managed.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('records.layout')}
          <select name="layout_id" required>
            {tracks.data?.flatMap((track) =>
              track.layouts.map((layout) => (
                <option key={layout.id} value={layout.id}>
                  {track.name} · {layout.name}
                </option>
              )),
            )}
          </select>
        </label>
        <label>
          {t('records.car')}
          <select name="car_id" required>
            {cars.data?.map((car) => (
              <option key={car.id} value={car.id}>
                {car.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('records.session')}
          <select name="category" defaultValue="race">
            <option value="qualifying">{t('records.category.qualifying')}</option>
            <option value="race">{t('records.category.race')}</option>
          </select>
        </label>
        <label>
          {t('records.time')}
          <input name="time" required pattern="\d+:\d{1,2}(\.\d{1,3})?" placeholder="3:09.296" />
        </label>
        <label>
          {t('records.holder')}
          <input name="driver_name" required maxLength={100} />
        </label>
        <label>
          {t('records.date')}
          <input name="date" type="date" required />
        </label>
        <label>
          {t('records.manualSourceLabel')}
          <input name="source" required maxLength={300} />
        </label>
      </ActionForm>
    </div>
  )
}
