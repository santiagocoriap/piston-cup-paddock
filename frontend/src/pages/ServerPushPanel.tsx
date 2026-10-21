import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Icon } from '../components/Icon'
import { errorMessage } from '../lib/errors'
import { PushStatus } from './PushStatus'

type Setup = components['schemas']['SetupOut']

// While the collector works, the panel asks for the state every 10 seconds.
const POLL_MS = 10_000

/** The clock time of an AC sun angle: 0 is 13:00, and 16 degrees is one hour. */
function clock(angle: number): string {
  const minutes = Math.round(13 * 60 + (angle * 60) / 16)
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}

/** "Enviar al servidor": what the server collector writes into the Content Manager preset,
 * and the state of the last push. The admin then starts the server in Content Manager. */
export function ServerPushPanel({ roundId }: { roundId: number }) {
  const { t } = useTranslation()
  const path = { round_id: roundId }
  const [setup, setSetup] = useState<Setup | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // The free slots for this push. Empty: the setting of the championship.
  const [slots, setSlots] = useState('')
  // The Content Manager preset of this push. Empty: the preset that the collector uses.
  const [preset, setPreset] = useState('')

  useEffect(() => {
    let stop = false
    async function load() {
      const { data, error } = await api.GET('/api/rounds/{round_id}/server-setup', { params: { path: { round_id: roundId } } })
      if (stop) return
      if (data) setSetup(data)
      else setError(errorMessage(t, error))
    }
    void load()
    const timer = window.setInterval(() => {
      setSetup((current) => {
        if (current?.latest && ['pending', 'waiting'].includes(current.latest.status)) void load()
        return current
      })
    }, POLL_MS)
    return () => {
      stop = true
      window.clearInterval(timer)
    }
  }, [roundId, t])

  async function send() {
    setError(null)
    setBusy(true)
    const body = {
      ...(slots === '' ? {} : { open_slots: Number(slots) }),
      ...(preset ? { preset } : {}),
    }
    const { data, error } = await api.POST('/api/rounds/{round_id}/server-push', { params: { path }, body })
    setBusy(false)
    if (data) setSetup(data)
    else setError(errorMessage(t, error))
  }

  if (!setup) {
    return error ? (
      <p role="alert" className="error">
        {error}
      </p>
    ) : (
      <p className="muted">{t('app.loading')}</p>
    )
  }
  const c = setup.conditions as Record<string, number | string | undefined>
  const conditionRows: [string, string][] = []
  if (typeof c.sun_angle === 'number') conditionRows.push([t('briefing.timeOfDay'), clock(c.sun_angle)])
  if (typeof c.weather === 'string') conditionRows.push([t('briefing.weather'), c.weather])
  if (typeof c.air_temp_c === 'number') conditionRows.push([t('briefing.airTemp'), `${c.air_temp_c} °C`])
  if (typeof c.air_temp_c === 'number' && typeof c.road_offset_c === 'number')
    conditionRows.push([t('briefing.trackTemp'), `${c.air_temp_c + c.road_offset_c} °C`])
  if (typeof c.grip_pct === 'number') conditionRows.push([t('briefing.grip'), `${c.grip_pct} %`])
  const latest = setup.latest

  return (
    <div className="server-push">
      <p className="muted">{t('serverPush.help')}</p>
      {!setup.has_collector && (
        <p className="warning" role="status">
          {t('serverPush.noCollector')}
        </p>
      )}
      <h4>{t('serverPush.track', { track: setup.track.key, layout: setup.track.layout || '—' })}</h4>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col" className="num">#</th>
              <th scope="col">{t('serverPush.driver')}</th>
              <th scope="col">{t('serverPush.car')}</th>
              <th scope="col" className="num">{t('serverPush.ballast')}</th>
              <th scope="col" className="num">{t('serverPush.restrictor')}</th>
              <th scope="col">{t('serverPush.guid')}</th>
            </tr>
          </thead>
          <tbody>
            {setup.entries.map((entry) => (
              <tr key={entry.number}>
                <td className="num">{entry.number}</td>
                <td>{entry.name}</td>
                <td className="mono">{entry.model}</td>
                <td className="num">{entry.ballast_kg} kg</td>
                <td className="num">{entry.restrictor_pct} %</td>
                <td>{entry.guid ? <Icon name="check" small /> : <span className="warning">{t('serverPush.noGuid')}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {conditionRows.length > 0 && (
        <dl className="lap-details">
          {conditionRows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {setup.warnings.length > 0 && (
        <ul className="auto-notes">
          {setup.warnings.map((warning) => {
            const [code, name] = warning.split(':')
            return <li key={warning}>{t(`serverPush.warnings.${code}`, { name })}</li>
          })}
        </ul>
      )}
      {setup.presets.length > 0 && (
        <label className="setting-number">
          {t('serverPush.preset')}
          <select value={preset || setup.preset} onChange={(e) => setPreset(e.target.value)}>
            {!setup.preset && <option value="">{t('serverPush.presetDefault')}</option>}
            {setup.presets.map((item) => (
              <option key={item.folder} value={item.folder}>
                {item.name}
              </option>
            ))}
          </select>
          <small className="muted">{t('serverPush.presetHelp')}</small>
        </label>
      )}
      <label className="setting-number">
        {t('serverPush.openSlots')}
        <input
          type="number"
          min={0}
          max={40}
          value={slots}
          placeholder={String(setup.open_slots)}
          onChange={(e) => setSlots(e.target.value)}
        />
        <small className="muted">{t('serverPush.openSlotsHelp', { count: setup.open_slots })}</small>
      </label>
      {latest && <PushStatus push={latest} collectorSeenAt={setup.collector_seen_at} />}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button type="button" onClick={send} disabled={busy}>
        {busy && <span className="spinner" aria-hidden="true" />}
        {t('serverPush.send')}
      </button>
    </div>
  )
}
