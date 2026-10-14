import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { TabEmpty } from './TabEmpty'

type Incidents = components['schemas']['IncidentsOut']
type Incident = components['schemas']['IncidentOut']
type Outcome = 'open' | 'no_action' | 'racing_incident' | 'penalty'

type Filters = { driver: string; attempt: string; lap: string; kind: string; minSpeed: number; outcome: string }
const NO_FILTERS: Filters = { driver: '', attempt: '', lap: '', kind: '', minSpeed: 0, outcome: '' }

/** Incidents from the collector events. Without events, the tab says why it is empty. */
export function IncidentsSection({ roundId }: { roundId: number }) {
  const { t } = useTranslation()
  const load = useLoad(
    () => api.GET('/api/rounds/{round_id}/incidents', { params: { path: { round_id: roundId } } }),
    [roundId],
  )
  const [override, setOverride] = useState<Incidents | null>(null)
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [selected, setSelected] = useState<number | null>(null)
  const data = override ?? load.data
  if (!data) return null
  if (!data.has_events) {
    return (
      <TabEmpty
        heading={t('incidents.title')}
        icon="alert"
        title={t('tabEmpty.noCollector')}
        text={t('tabEmpty.incidents')}
      />
    )
  }

  const drivers = [...new Set(data.incidents.flatMap((i) => i.cars))].sort()
  const attempts = [...new Set(data.incidents.map((i) => i.attempt))].sort((a, b) => a - b)
  const laps = [...new Set(data.incidents.map((i) => i.lap).filter((l) => l !== null && l !== undefined))].sort((a, b) => (a as number) - (b as number))
  const shown = data.incidents.filter(
    (i) =>
      (!filters.driver || i.cars.includes(filters.driver)) &&
      (!filters.attempt || String(i.attempt) === filters.attempt) &&
      (!filters.lap || String(i.lap) === filters.lap) &&
      (!filters.kind || i.kind === filters.kind) &&
      i.max_speed >= filters.minSpeed &&
      (!filters.outcome || (i.review?.outcome ?? 'open') === filters.outcome),
  )
  const current = data.incidents.find((i) => i.key === selected) ?? null
  const set = (name: keyof Filters, value: string) =>
    setFilters((old) => ({ ...old, [name]: name === 'minSpeed' ? Number(value) : value }))

  return (
    <section aria-label={t('incidents.title')}>
      <h2>{t('incidents.title')}</h2>
      <p className="muted">{t('incidents.policy', { seconds: data.gap_seconds })}</p>
      <div className="forms" role="group" aria-label={t('incidents.filters')}>
        <label>
          {t('incidents.driver')}
          <select value={filters.driver} onChange={(e) => set('driver', e.target.value)}>
            <option value="">{t('incidents.all')}</option>
            {drivers.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          {t('incidents.attempt')}
          <select value={filters.attempt} onChange={(e) => set('attempt', e.target.value)}>
            <option value="">{t('incidents.all')}</option>
            {attempts.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('incidents.lap')}
          <select value={filters.lap} onChange={(e) => set('lap', e.target.value)}>
            <option value="">{t('incidents.all')}</option>
            {laps.map((n) => (
              <option key={String(n)} value={String(n)}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('incidents.kindLabel')}
          <select value={filters.kind} onChange={(e) => set('kind', e.target.value)}>
            <option value="">{t('incidents.all')}</option>
            <option value="car">{t('incidents.kind.car')}</option>
            <option value="env">{t('incidents.kind.env')}</option>
          </select>
        </label>
        <label>
          {t('incidents.minSpeed', { value: filters.minSpeed })}
          <input type="range" min={0} max={200} step={10} value={filters.minSpeed} onChange={(e) => set('minSpeed', e.target.value)} />
        </label>
        <label>
          {t('incidents.outcomeLabel')}
          <select value={filters.outcome} onChange={(e) => set('outcome', e.target.value)}>
            <option value="">{t('incidents.all')}</option>
            {(['open', 'no_action', 'racing_incident', 'penalty'] as const).map((o) => (
              <option key={o} value={o}>
                {t(`incidents.outcome.${o}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <IncidentMap incidents={shown} selected={selected} onSelect={setSelected} />
      <ul className="list">
        {shown.map((incident) => (
          <li key={incident.key}>
            <button type="button" className="link-button" onClick={() => setSelected(incident.key)}>
              {t('incidents.summary', {
                attempt: incident.attempt,
                lap: incident.lap ?? '—',
                cars: incident.cars.join(' + '),
                speed: Math.round(incident.max_speed),
              })}
            </button>{' '}
            <span className="badge">{t(`incidents.kind.${incident.kind}`)}</span>
            <span className="badge">{t(`incidents.outcome.${incident.review?.outcome ?? 'open'}`)}</span>
          </li>
        ))}
      </ul>
      {current && (
        <IncidentDetail
          key={current.key}
          roundId={roundId}
          incident={current}
          canReview={data.can_review}
          onChange={setOverride}
        />
      )}
    </section>
  )
}

/** A heatmap and markers at the world position of the first event. The track has no map
 *  yet, so the plot shows only the incident positions. */
function IncidentMap({ incidents, selected, onSelect }: { incidents: Incident[]; selected: number | null; onSelect: (key: number) => void }) {
  const { t } = useTranslation()
  const placed = incidents.filter((i) => i.x !== null && i.x !== undefined && i.z !== null && i.z !== undefined)
  if (placed.length === 0) return <p className="muted">{t('incidents.noPositions')}</p>
  const xs = placed.map((i) => i.x as number)
  const zs = placed.map((i) => i.z as number)
  const [minX, maxX, minZ, maxZ] = [Math.min(...xs), Math.max(...xs), Math.min(...zs), Math.max(...zs)]
  const span = Math.max(maxX - minX, maxZ - minZ, 1)
  const size = 400
  const px = (x: number) => 20 + ((x - minX) / span) * (size - 40)
  const pz = (z: number) => 20 + ((z - minZ) / span) * (size - 40)
  return (
    <figure className="incident-map">
      <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={t('incidents.map')}>
        {placed.map((i) => (
          <circle key={`heat-${i.key}`} cx={px(i.x as number)} cy={pz(i.z as number)} r={24} className="heat" />
        ))}
        {placed.map((i) => (
          <circle
            key={i.key}
            cx={px(i.x as number)}
            cy={pz(i.z as number)}
            r={i.key === selected ? 8 : 6}
            className={`marker ${i.kind}`}
            role="button"
            tabIndex={0}
            aria-label={i.cars.join(' + ')}
            onClick={() => onSelect(i.key)}
            onKeyDown={(e) => e.key === 'Enter' && onSelect(i.key)}
          />
        ))}
      </svg>
      <figcaption className="muted">{t('incidents.mapHelp')}</figcaption>
    </figure>
  )
}

function IncidentDetail({
  roundId,
  incident,
  canReview,
  onChange,
}: {
  roundId: number
  incident: Incident
  canReview: boolean
  onChange: (next: Incidents) => void
}) {
  const { t, i18n } = useTranslation()
  const [error, setError] = useState<string | null>(null)

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const { data, error } = await api.PUT('/api/rounds/{round_id}/incidents/{key}/review', {
      params: { path: { round_id: roundId, key: incident.key } },
      body: { outcome: form.get('outcome') as Outcome, note: String(form.get('note') ?? '') },
    })
    if (data) onChange(data)
    else setError(errorMessage(t, error))
  }

  return (
    <div className="card" role="region" aria-label={t('incidents.detail')}>
      <h3>{t('incidents.detail')}</h3>
      <ul>
        {incident.events.map((e) => (
          <li key={e.id}>
            {formatDateTime(e.at, i18n.language)} · {e.car}
            {e.other ? ` ↔ ${e.other}` : ` · ${t('incidents.kind.env')}`} · {Math.round(e.speed_kmh)} km/h
          </li>
        ))}
      </ul>
      {incident.review && (
        <p>
          {t(`incidents.outcome.${incident.review.outcome}`)}
          {incident.review.note && ` — ${incident.review.note}`}{' '}
          <span className="muted">({incident.review.reviewed_by})</span>
        </p>
      )}
      {canReview && (
        <form onSubmit={save} aria-label={t('incidents.review')}>
          <label>
            {t('incidents.outcomeLabel')}
            <select name="outcome" defaultValue={incident.review?.outcome ?? 'open'}>
              {(['open', 'no_action', 'racing_incident', 'penalty'] as const).map((o) => (
                <option key={o} value={o}>
                  {t(`incidents.outcome.${o}`)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('incidents.note')}
            <textarea name="note" defaultValue={incident.review?.note ?? ''} maxLength={1000} />
          </label>
          <button type="submit">{t('incidents.saveReview')}</button>
        </form>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  )
}
