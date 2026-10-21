import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { ActionForm } from '../components/ActionForm'
import { Combobox } from '../components/Combobox'
import { Dialog } from '../components/Dialog'
import { errorMessage } from '../lib/errors'
import { useLoad } from '../lib/useLoad'

/** "Unirme a una temporada" for a driver. The season either lets the driver in at once (free
 * join) or takes a request that an admin decides. `onDone` gets "joined" or "requested". */
export function JoinSeasonButton({ onDone }: { onDone: (status: string, season: string) => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" className="secondary" onClick={() => setOpen(true)}>
        {t('join.button')}
      </button>
      <Dialog open={open} title={t('join.title')} onClose={() => setOpen(false)}>
        {open && (
          <JoinSeasonForm
            onDone={(status, season) => {
              setOpen(false)
              onDone(status, season)
            }}
          />
        )}
      </Dialog>
    </>
  )
}

function JoinSeasonForm({ onDone }: { onDone: (status: string, season: string) => void }) {
  const { t } = useTranslation()
  const options = useLoad(() => api.GET('/api/join/seasons'), [])
  const cars = useLoad(() => api.GET('/api/catalog/cars'), [])
  const [seasonId, setSeasonId] = useState('')
  const [carId, setCarId] = useState('')
  const seasons = (options.data?.seasons ?? []).filter((s) => s.mine !== 'entered')
  const chosen = seasons.find((s) => String(s.season_id) === seasonId)
  const free = chosen?.free_join ?? false
  return (
    <ActionForm
      title={t('join.title')}
      submitLabel={free ? t('join.submitFree') : t('join.submitRequest')}
      onSubmit={async (form) => {
        if (!seasonId || !carId) return { detail: 'join_incomplete' }
        const { data, error } = await api.POST('/api/seasons/{season_id}/join', {
          params: { path: { season_id: Number(seasonId) } },
          body: {
            car_id: Number(carId),
            number: Number(form.get('number')),
            note: String(form.get('note') ?? ''),
          },
        })
        if (!error && data) onDone(data.status, chosen?.season_name ?? '')
        return error
      }}
    >
      <p className="muted">{t('join.help')}</p>
      {options.data && seasons.length === 0 && <p>{t('join.none')}</p>}
      <label>
        {t('join.season')}
        <select value={seasonId} onChange={(event) => setSeasonId(event.target.value)} required>
          <option value="" disabled>
            {t('common.select')}
          </option>
          {seasons.map((s) => (
            <option key={s.season_id} value={s.season_id} disabled={s.mine === 'pending'}>
              {s.championship_name} · {s.season_name}
              {s.free_join ? ` · ${t('join.free')}` : ''}
              {s.mine === 'pending' ? ` · ${t('join.pending')}` : ''}
            </option>
          ))}
        </select>
      </label>
      {chosen && <p className="muted">{t(free ? 'join.freeHelp' : 'join.requestHelp')}</p>}
      <Combobox
        label={t('season.car')}
        options={(cars.data ?? [])
          .filter((car) => !chosen?.car_ids || chosen.car_ids.includes(car.id))
          .map((car) => ({ value: String(car.id), label: car.name }))}
        value={carId}
        onChange={setCarId}
        emptyText={t('join.noCars')}
      />
      <label>
        {t('season.number')}
        <input name="number" type="number" min={1} max={999} required />
      </label>
      {chosen && !free && (
        <label>
          {t('join.note')}
          <input name="note" maxLength={300} />
        </label>
      )}
    </ActionForm>
  )
}

/** The requests that wait for an admin of the season. Nothing shows when there are none. */
export function JoinRequestsPanel({ seasonId, onChange }: { seasonId: number; onChange: () => void }) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const requests = useLoad(() => api.GET('/api/seasons/{season_id}/join-requests', { params: { path } }), [seasonId])
  const [numbers, setNumbers] = useState<Record<number, string>>({})
  const [error, setError] = useState<string | null>(null)
  const list = requests.data ?? []
  if (list.length === 0) return null

  async function decide(id: number, approve: boolean, asked: number) {
    setError(null)
    const params = { path: { request_id: id } }
    const { error: failed } = approve
      ? await api.POST('/api/join-requests/{request_id}/approve', {
          params,
          body: { number: Number(numbers[id] || asked) },
        })
      : await api.POST('/api/join-requests/{request_id}/decline', { params })
    if (failed) return setError(errorMessage(t, failed))
    requests.reload()
    onChange()
  }

  return (
    <div className="join-requests" role="region" aria-label={t('join.requests', { count: list.length })}>
      <h3>{t('join.requests', { count: list.length })}</h3>
      <ul>
        {list.map((request) => (
          <li key={request.id}>
            <span>
              <b>{request.driver_name}</b>
              <span className="muted">{request.car_name}</span>
              {request.note && <span className="muted">«{request.note}»</span>}
            </span>
            <label className="join-number">
              <span className="sr-only">{t('season.number')}</span>
              <input
                type="number"
                min={1}
                max={999}
                value={numbers[request.id] ?? String(request.number)}
                onChange={(event) => setNumbers({ ...numbers, [request.id]: event.target.value })}
              />
            </label>
            <button type="button" className="small" onClick={() => void decide(request.id, true, request.number)}>
              {t('join.approve')}
            </button>
            <button type="button" className="secondary small" onClick={() => void decide(request.id, false, request.number)}>
              {t('join.decline')}
            </button>
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  )
}
