import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { errorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type Fields = components['schemas']['RulesFields']
type Version = components['schemas']['RulesVersionOut']
type PreviewRow = components['schemas']['PreviewRowOut']

const numbers = (text: string) =>
  text
    .split(/[\s,;]+/)
    .filter(Boolean)
    .map(Number)

function fieldsFrom(form: FormData): Fields {
  const value = (name: string) => Number(form.get(name) ?? 0)
  return {
    points_by_position: numbers(String(form.get('points_by_position') ?? '')),
    pole_bonus: value('pole_bonus'),
    fastest_lap_bonus: value('fastest_lap_bonus'),
    ballast_steps: numbers(String(form.get('ballast_steps') ?? '')),
    restrictor_steps: numbers(String(form.get('restrictor_steps') ?? '')),
    ballast_cap: value('ballast_cap'),
    restrictor_cap: value('restrictor_cap'),
    ballast_reduction: value('ballast_reduction'),
    restrictor_reduction: value('restrictor_reduction'),
  }
}

/** The rules of the season, the version history, and the editor for admins. */
export function RulesSection({ seasonId, adminView }: { seasonId: number; adminView: boolean }) {
  const { t, i18n } = useTranslation()
  const path = { season_id: seasonId }
  const load = useLoad(() => api.GET('/api/seasons/{season_id}/rules', { params: { path } }), [seasonId])
  const [preview, setPreview] = useState<PreviewRow[] | null>(null)
  const [message, setMessage] = useState<{ kind: 'error' | 'status'; text: string } | null>(null)
  const data = load.data
  if (!data) return null
  const [current, ...older] = data.versions

  async function showPreview(form: HTMLFormElement) {
    setMessage(null)
    const { data: rows, error } = await api.POST('/api/seasons/{season_id}/rules/preview', {
      params: { path },
      body: fieldsFrom(new FormData(form)),
    })
    if (rows) setPreview(rows)
    else setMessage({ kind: 'error', text: errorMessage(t, error) })
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    if (form.get('recalculate') === 'on' && !window.confirm(t('rulesEditor.confirmRecalculate'))) return
    const { error } = await api.POST('/api/seasons/{season_id}/rules', {
      params: { path },
      body: { ...fieldsFrom(form), reason: String(form.get('reason')), recalculate: form.get('recalculate') === 'on' },
    })
    if (error) setMessage({ kind: 'error', text: errorMessage(t, error) })
    else {
      setPreview(null)
      setMessage({ kind: 'status', text: t('rulesEditor.saved') })
      load.reload()
    }
  }

  return (
    <section aria-label={t('rulesEditor.title')}>
      <h2>{t('rulesEditor.title')}</h2>
      <RulesSummary version={current} />
      {older.length > 0 && (
        <details>
          <summary>{t('rulesEditor.history', { count: older.length })}</summary>
          <ul className="list">
            {data.versions.map((v) => (
              <li key={v.number}>
                <strong>{t('rulesEditor.version', { number: v.number })}</strong> · {formatDateTime(v.created_at, i18n.language)}
                {v.created_by && ` · ${v.created_by}`}
                {v.reason && ` · ${v.reason}`}
                {v.number > 1 && ` · ${t(v.recalculated ? 'rulesEditor.recalculated' : 'rulesEditor.futureOnly')}`}
                <RulesSummary version={v} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {adminView && data.can_edit && (
        <form className="card" onSubmit={save} aria-label={t('rulesEditor.edit')}>
          <h3>{t('rulesEditor.edit')}</h3>
          <label>
            {t('rulesEditor.points')}
            <input name="points_by_position" defaultValue={current.points_by_position.join(', ')} required />
          </label>
          <label>
            {t('rulesEditor.pole')}
            <input name="pole_bonus" type="number" min={0} max={50} defaultValue={current.pole_bonus} />
          </label>
          <label>
            {t('rulesEditor.fastestLap')}
            <input name="fastest_lap_bonus" type="number" min={0} max={50} defaultValue={current.fastest_lap_bonus} />
          </label>
          <label>
            {t('rulesEditor.ballastSteps')}
            <input name="ballast_steps" defaultValue={current.ballast_steps.join(', ')} />
          </label>
          <label>
            {t('rulesEditor.ballastCap')}
            <input name="ballast_cap" type="number" min={0} max={200} defaultValue={current.ballast_cap} />
          </label>
          <label>
            {t('rulesEditor.ballastReduction')}
            <input name="ballast_reduction" type="number" min={0} max={200} defaultValue={current.ballast_reduction} />
          </label>
          <label>
            {t('rulesEditor.restrictorSteps')}
            <input name="restrictor_steps" defaultValue={current.restrictor_steps.join(', ')} />
          </label>
          <label>
            {t('rulesEditor.restrictorCap')}
            <input name="restrictor_cap" type="number" min={0} max={100} defaultValue={current.restrictor_cap} />
          </label>
          <label>
            {t('rulesEditor.restrictorReduction')}
            <input name="restrictor_reduction" type="number" min={0} max={100} defaultValue={current.restrictor_reduction} />
          </label>
          <label>
            {t('rulesEditor.reason')}
            <input name="reason" required maxLength={500} />
          </label>
          <label className="check">
            <input type="checkbox" name="recalculate" />
            {t('rulesEditor.recalculateLabel')}
          </label>
          <p className="muted">{t('rulesEditor.recalculateHelp')}</p>
          <button type="button" onClick={(e) => showPreview(e.currentTarget.form!)}>
            {t('rulesEditor.preview')}
          </button>{' '}
          <button type="submit">{t('rulesEditor.save')}</button>
          {preview && <Preview rows={preview} />}
        </form>
      )}
      {message && (
        <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'success'}>
          {message.text}
        </p>
      )}
    </section>
  )
}

function RulesSummary({ version }: { version: Version }) {
  const { t } = useTranslation()
  return (
    <p className="muted">
      {t('rulesEditor.summary', {
        number: version.number,
        points: version.points_by_position.join('-'),
        pole: version.pole_bonus,
        fastest: version.fastest_lap_bonus,
        ballast: version.ballast_steps.join('/'),
        ballastCap: version.ballast_cap,
        restrictor: version.restrictor_steps.join('/'),
        restrictorCap: version.restrictor_cap,
      })}
    </p>
  )
}

function Preview({ rows }: { rows: PreviewRow[] }) {
  const { t } = useTranslation()
  return (
    <div className="table-wrap">
      <table aria-label={t('rulesEditor.previewTable')}>
        <thead>
          <tr>
            <th scope="col">{t('season.driver')}</th>
            <th scope="col">{t('rulesEditor.now')}</th>
            <th scope="col">{t('rulesEditor.withNew')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.entry_id}>
              <td>{row.driver_name}</td>
              <td>
                P{row.current_rank} · {row.current_points} pts
              </td>
              <td className={row.new_rank < row.current_rank ? 'faster' : row.new_rank > row.current_rank ? 'slower' : undefined}>
                P{row.new_rank} · {row.new_points} pts
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
