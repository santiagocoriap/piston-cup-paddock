import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { Dialog } from '../components/Dialog'
import { EmptyState } from '../components/EmptyState'
import { Icon } from '../components/Icon'
import { Loading } from '../components/Layout'
import { formatDateTime, formatLapTime } from '../lib/format'
import { initials } from '../lib/initials'
import { medal } from '../lib/medal'
import { useLoad } from '../lib/useLoad'
import { useMode } from '../session'
import { Breadcrumbs } from '../components/Breadcrumbs'

type Board = components['schemas']['BoardOut']
type RecordLap = components['schemas']['RecordLapOut']
type RecordsData = components['schemas']['RecordsOut']
type Championship = components['schemas']['ChampionshipOut']
type Filters = { layout: string; car: string; carClass: string; category: string; season: string; overall: boolean }

const NO_FILTERS: Filters = { layout: '', car: '', carClass: '', category: '', season: '', overall: false }

export function RecordsPage() {
  const { t } = useTranslation()
  const { mode } = useMode()
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [adding, setAdding] = useState(false)
  const sessionLabel = useId()
  const records = useLoad(
    () =>
      api.GET('/api/records', {
        params: {
          query: {
            ...(filters.layout ? { layout_id: Number(filters.layout) } : {}),
            ...(filters.car && !filters.overall && !filters.carClass ? { car_id: Number(filters.car) } : {}),
            ...(filters.carClass ? { car_class_id: Number(filters.carClass) } : {}),
            ...(filters.category ? { category: filters.category as 'race' | 'qualifying' } : {}),
            ...(filters.season ? { season_id: Number(filters.season) } : {}),
            ...(filters.overall ? { overall: true } : {}),
          },
        },
      }),
    [filters.layout, filters.car, filters.carClass, filters.category, filters.season, filters.overall],
  )
  const championships = useLoad(
    () => (mode === 'admin' ? api.GET('/api/championships') : Promise.resolve({ data: [] as Championship[] })),
    [mode],
  )
  const managed = championships.data?.filter((c) => c.can_manage) ?? []
  const canAdd = mode === 'admin' && managed.length > 0
  const set = (name: keyof Filters, value: string | boolean) => setFilters((old) => ({ ...old, [name]: value }))
  const filtered = Object.values(filters).some(Boolean)

  return (
    <section>
      <Breadcrumbs items={[{ label: t('nav.records') }]} />
      <header className="page-head">
        <div>
          <h1>{t('records.title')}</h1>
          <p className="muted">{t('records.help')}</p>
        </div>
        <div className="page-actions">
          <a className="button-link secondary-link" href="/api/records/export.csv" download>
            <Icon name="download" small />
            {t('exports.records')}
          </a>
          {canAdd && (
            <button type="button" onClick={() => setAdding(true)}>
              <Icon name="plus" small />
              {t('records.add')}
            </button>
          )}
        </div>
      </header>
      {!records.data ? (
        <Loading failed={records.failed} />
      ) : (
        <>
          <div className="forms record-filters" role="group" aria-label={t('records.filters')}>
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
              <select value={filters.car} disabled={filters.overall || Boolean(filters.carClass)} onChange={(e) => set('car', e.target.value)}>
                <option value="">{t('records.allCars')}</option>
                {records.data.cars.map((car) => (
                  <option key={car.id} value={car.id}>
                    {car.name}
                  </option>
                ))}
              </select>
            </label>
            {records.data.classes.length > 0 && (
              <label className="inline-filter">
                {t('records.carClass')}
                <select value={filters.carClass} onChange={(e) => set('carClass', e.target.value)}>
                  <option value="">{t('records.noClass')}</option>
                  {records.data.classes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
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
            <div className="segmented-field">
              <span id={sessionLabel}>{t('records.session')}</span>
              <div className="segmented" role="radiogroup" aria-labelledby={sessionLabel}>
              {[
                ['', t('records.sessionAll')],
                ['qualifying', t('records.sessionShort.qualifying')],
                ['race', t('records.sessionShort.race')],
              ].map(([value, label]) => (
                <label key={value}>
                  <input
                    type="radio"
                    name="records-session"
                    value={value}
                    checked={filters.category === value}
                    onChange={() => set('category', value)}
                  />
                  <span>{label}</span>
                </label>
              ))}
              </div>
            </div>
            <label className="switch">
              <input type="checkbox" role="switch" checked={filters.overall} onChange={(e) => set('overall', e.target.checked)} />
              <span className="switch-track" aria-hidden="true" />
              {t('records.overall')}
            </label>
          </div>
          <ActiveFilters
            filters={filters}
            data={records.data}
            onRemove={(name) => set(name, NO_FILTERS[name])}
            onClear={() => setFilters(NO_FILTERS)}
          />
          {records.data.boards.length === 0 ? (
            filtered ? (
              <EmptyState icon="timer" title={t('records.noMatch')} text={t('records.noMatchHelp')}>
                <button type="button" className="secondary" onClick={() => setFilters(NO_FILTERS)}>
                  {t('records.clearFilters')}
                </button>
              </EmptyState>
            ) : (
              <EmptyState icon="timer" title={t('records.emptyTitle')} text={t('records.empty')}>
                {canAdd && (
                  <button type="button" onClick={() => setAdding(true)}>
                    <Icon name="plus" small />
                    {t('records.addManual')}
                  </button>
                )}
              </EmptyState>
            )
          ) : (
            <div className="boards">
              {records.data.boards.map((board) => (
                <BoardCard key={`${board.layout_id}-${board.car_id}-${board.category}`} board={board} onChange={records.reload} />
              ))}
            </div>
          )}
        </>
      )}
      {canAdd && (
        <Dialog open={adding} title={t('records.addManual')} onClose={() => setAdding(false)}>
          <ManualRecordForm
            championships={managed}
            onSaved={() => {
              setAdding(false)
              records.reload()
            }}
          />
        </Dialog>
      )}
    </section>
  )
}

/** The filters that are on, as chips. Each chip removes its filter. */
function ActiveFilters({
  filters,
  data,
  onRemove,
  onClear,
}: {
  filters: Filters
  data: RecordsData
  onRemove: (name: keyof Filters) => void
  onClear: () => void
}) {
  const { t } = useTranslation()
  const name = (list: { id: number; name: string }[], id: string) => list.find((item) => String(item.id) === id)?.name ?? id
  const chips: [keyof Filters, string][] = []
  if (filters.layout) chips.push(['layout', name(data.layouts, filters.layout)])
  if (filters.car && !filters.overall && !filters.carClass) chips.push(['car', name(data.cars, filters.car)])
  if (filters.carClass) chips.push(['carClass', name(data.classes, filters.carClass)])
  if (filters.season) chips.push(['season', name(data.seasons, filters.season)])
  if (filters.category) chips.push(['category', t(`records.sessionShort.${filters.category}`)])
  if (filters.overall) chips.push(['overall', t('records.overall')])
  if (chips.length === 0) return null
  return (
    <ul className="filter-chips" aria-label={t('records.activeFilters')}>
      {chips.map(([key, label]) => (
        <li key={key} className="filter-chip">
          {label}
          <button type="button" aria-label={t('records.removeFilter', { name: label })} onClick={() => onRemove(key)}>
            <Icon name="close" small />
          </button>
        </li>
      ))}
      {chips.length > 1 && (
        <li>
          <button type="button" className="link" onClick={onClear}>
            {t('records.clearFilters')}
          </button>
        </li>
      )}
    </ul>
  )
}

function gapText(ms: number): string {
  return ms < 60_000 ? `+${(ms / 1000).toFixed(3)}` : `+${formatLapTime(ms)}`
}

function BoardCard({ board, onChange }: { board: Board; onChange: () => void }) {
  const { t, i18n } = useTranslation()
  const { mode } = useMode()
  const car = board.car_id ? board.car_name : board.car_name || t('records.allCars')
  const title = `${t(`records.category.${board.category}`)}: ${board.track_name} · ${board.layout_name} · ${car}`
  const record = board.record_ms ?? board.ranking[0]?.lap_time_ms ?? 0
  const maxGap = Math.max(1, ...board.ranking.map((lap) => lap.lap_time_ms - record))
  return (
    <article className="card board" aria-label={title}>
      <header className="board-head">
        <span className={`session-pill session-${board.category}`}>{t(`records.sessionShort.${board.category}`)}</span>
        <h2 className="board-title">
          {board.track_name} · {board.layout_name}
          <span className="board-car">{car}</span>
        </h2>
      </header>
      {board.record_ms ? (
        <div className="record-hero">
          <p className="record-time">
            {formatLapTime(board.record_ms)}
            {board.holders.length > 1 && <span className="badge">{t('records.shared')}</span>}
          </p>
          <p className="record-holder muted">
            {t('records.holderLabel')} <strong>{board.holders.map((h) => h.driver_name).join(', ')}</strong>
          </p>
        </div>
      ) : (
        <p className="muted">—</p>
      )}

      {board.ranking.length > 0 && (
        <table className="leaderboard">
          <caption className="sr-only">{t('records.ranking')}</caption>
          <thead>
            <tr>
              <th scope="col">{t('records.position')}</th>
              <th scope="col">{t('records.holder')}</th>
              <th scope="col" className="num">
                {t('records.lapTime')}
              </th>
              <th scope="col" className="num">
                {t('records.gap')}
              </th>
            </tr>
          </thead>
          <tbody>
            {board.ranking.map((lap, index) => {
              const gap = lap.lap_time_ms - record
              // Longer is faster: the record fills the bar, the slowest lap fills a fifth.
              const pace = gap <= 0 ? 100 : 100 - (gap / maxGap) * 80
              return (
                <tr key={lap.lap_id} className={medal(index + 1) || undefined}>
                  <td>
                    <span className="position">{index + 1}</span>
                  </td>
                  <td>
                    <span className="driver">
                      <span className="avatar" aria-hidden="true">
                        {initials(lap.driver_name)}
                      </span>
                      {lap.driver_name}
                    </span>
                    <span className="pace" aria-hidden="true">
                      <span className="pace-bar" style={{ width: `${pace}%` }} />
                    </span>
                  </td>
                  <td className="num mono">{formatLapTime(lap.lap_time_ms)}</td>
                  <td className="num mono gap">{gap <= 0 ? '—' : gapText(gap)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      {board.holders.length > 0 && (
        <details>
          <summary>{t('records.details')}</summary>
          {board.holders.map((holder) => (
            <LapDetails key={holder.lap_id} lap={holder} onChange={onChange} />
          ))}
        </details>
      )}

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
function ManualRecordForm({ championships, onSaved }: { championships: Championship[]; onSaved: () => void }) {
  const { t } = useTranslation()
  const tracks = useLoad(() => api.GET('/api/catalog/tracks'), [])
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  return (
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
          {championships.map((c) => (
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
  )
}
