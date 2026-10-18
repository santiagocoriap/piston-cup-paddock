import { useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Icon } from '../components/Icon'
import { errorMessage } from '../lib/errors'
import { currentTimeZone, isoToLocalInput, localInputToIso } from '../lib/format'

type Round = components['schemas']['RoundOut']
type Row = { round: Round; date: string }

/** The calendar of a season for an admin: drag a round to its place (or use the arrows), and
 * pick its date and time. "Guardar" saves the order and the dates in one go. */
export function CalendarOrder({
  seasonId,
  rounds,
  onSaved,
}: {
  seasonId: number
  rounds: Round[]
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const zone = currentTimeZone()
  const [rows, setRows] = useState<Row[]>(() =>
    [...rounds]
      .sort((a, b) => a.number - b.number)
      .map((round) => ({ round, date: round.scheduled_at ? isoToLocalInput(round.scheduled_at, zone) : '' })),
  )
  const [dragged, setDragged] = useState<number | null>(null)
  const [over, setOver] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  function move(from: number, to: number) {
    if (to < 0 || to >= rows.length || from === to) return
    setSaved(false)
    setRows((old) => {
      const next = [...old]
      const [row] = next.splice(from, 1)
      next.splice(to, 0, row)
      return next
    })
  }

  function setDate(index: number, date: string) {
    setSaved(false)
    setRows((old) => old.map((row, i) => (i === index ? { ...row, date } : row)))
  }

  async function save() {
    setError(null)
    setBusy(true)
    try {
      const { error: orderError } = await api.PUT('/api/seasons/{season_id}/round-order', {
        params: { path: { season_id: seasonId } },
        body: { round_ids: rows.map((row) => row.round.id) },
      })
      if (orderError) {
        setError(errorMessage(t, orderError))
        return
      }
      for (const row of rows) {
        const before = row.round.scheduled_at ? isoToLocalInput(row.round.scheduled_at, zone) : ''
        if (!row.date || row.date === before) continue
        const { error } = await api.PATCH('/api/rounds/{round_id}/calendar', {
          params: { path: { round_id: row.round.id } },
          body: { scheduled_at: localInputToIso(row.date, zone) },
        })
        if (error) {
          setError(errorMessage(t, error))
          return
        }
      }
      setSaved(true)
      onSaved()
    } finally {
      setBusy(false)
    }
  }

  const dragProps = (index: number) => ({
    draggable: true,
    onDragStart: (event: DragEvent) => {
      setDragged(index)
      event.dataTransfer.effectAllowed = 'move'
      // Firefox needs data to start a drag.
      event.dataTransfer.setData('text/plain', String(index))
    },
    onDragOver: (event: DragEvent) => {
      event.preventDefault()
      setOver(index)
    },
    onDrop: (event: DragEvent) => {
      event.preventDefault()
      if (dragged !== null) move(dragged, index)
      setDragged(null)
      setOver(null)
    },
    onDragEnd: () => {
      setDragged(null)
      setOver(null)
    },
  })

  return (
    <div className="modal-body calendar-order">
      <h3>{t('calendarOrder.title')}</h3>
      <p className="muted">{t('calendarOrder.help', { zone: zone.replaceAll('_', ' ') })}</p>
      <ol className="order-list">
        {rows.map((row, index) => (
          <li
            key={row.round.id}
            className={[
              'order-row',
              dragged === index ? 'dragging' : '',
              over === index && dragged !== index ? 'drop-here' : '',
              row.round.cancelled ? 'cancelled' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            {...dragProps(index)}
          >
            <span className="order-grip" aria-hidden="true">
              ⠿
            </span>
            <span className="order-rank">{index + 1}</span>
            <span className="order-name">
              <b>{row.round.track_name}</b>
              <span className="muted">
                {row.round.layout_name}
                {row.round.origin === 'voted' && <> · {t('calendarOrder.voted')}</>}
              </span>
            </span>
            <input
              type="datetime-local"
              value={row.date}
              onChange={(event) => setDate(index, event.target.value)}
              aria-label={t('calendarOrder.date', { track: row.round.track_name })}
            />
            <span className="order-moves">
              <button
                type="button"
                className="icon-button"
                onClick={() => move(index, index - 1)}
                disabled={index === 0}
                aria-label={t('calendarOrder.up', { track: row.round.track_name })}
              >
                <Icon name="chevron" small />
              </button>
              <button
                type="button"
                className="icon-button down"
                onClick={() => move(index, index + 1)}
                disabled={index === rows.length - 1}
                aria-label={t('calendarOrder.down', { track: row.round.track_name })}
              >
                <Icon name="chevron" small />
              </button>
            </span>
          </li>
        ))}
      </ol>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="success">
          {t('calendarOrder.saved')}
        </p>
      )}
      <div className="settings-actions">
        <button type="button" onClick={save} disabled={busy}>
          {busy && <span className="spinner" aria-hidden="true" />}
          {t('common.save')}
        </button>
      </div>
    </div>
  )
}
