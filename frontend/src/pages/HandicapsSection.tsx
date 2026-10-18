import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { AdminActions } from '../components/AdminActions'
import { useLoad } from '../lib/useLoad'

type Step = components['schemas']['StepOut']
type Mode = components['schemas']['AdjustmentIn']['mode']
type RoundOut = components['schemas']['RoundOut']

const value = (kg: number, pct: number) => `${kg} kg · ${pct} %`
const signed = (n: number) => (n > 0 ? `+${n}` : String(n))

function stepLine(t: TFunction, step: Step): string {
  const place =
    step.status === 'dsq' ? 'DSQ' : step.status === 'dnf' ? `DNF P${step.position}` : `P${step.position}`
  const outcome = t(`handicaps.outcome.${step.outcome}`, { wins: step.season_wins, place })
  const change = `${signed(step.change_kg)} kg ${signed(step.change_pct)} %`
  return t('handicaps.stepLine', {
    number: step.round_number,
    before: value(step.before_kg, step.before_pct),
    outcome,
    change,
    after: value(step.after_kg, step.after_pct),
  })
}

/** The ballast and restrictor of each driver for each round, with the explanation. */
export function HandicapsSection({
  seasonId,
  rounds,
  adminView,
  refresh = 0,
}: {
  seasonId: number
  rounds: RoundOut[]
  adminView: boolean
  refresh?: number
}) {
  const { t } = useTranslation()
  const path = { season_id: seasonId }
  const data = useLoad(
    () => api.GET('/api/seasons/{season_id}/handicaps', { params: { path } }),
    [seasonId, refresh],
  )
  if (!data.data || data.data.entries.length === 0) return null
  const { entries, rules, next_round_number } = data.data
  const raced = entries[0]?.rounds ?? []

  return (
    <>
      <div className="section-head">
        <h2>{t('handicaps.title')}</h2>
        {adminView && (
          <AdminActions
            actions={[
              {
                id: 'adjust',
                label: t('handicaps.adjust'),
                content: (close) => (
                  <ActionForm
                    title={t('handicaps.adjust')}
                    submitLabel={t('common.save')}
                    onDone={close}
                    onSubmit={async (form) => {
                      const { error } = await api.POST('/api/seasons/{season_id}/handicaps/adjustments', {
                        params: { path },
                        body: {
                          entry_id: Number(form.get('entry_id')),
                          round_id: Number(form.get('round_id')),
                          ballast_kg: Number(form.get('ballast_kg')),
                          restrictor_pct: Number(form.get('restrictor_pct')),
                          mode: form.get('mode') as Mode,
                          reason: String(form.get('reason') ?? ''),
                        },
                      })
                      if (!error) data.reload()
                      return error
                    }}
                  >
                    <div className="field-row">
                      <label>
                        {t('handicaps.driver')}
                        <select name="entry_id" required defaultValue="">
                          <option value="" disabled>
                            {t('common.select')}
                          </option>
                          {entries.map((entry) => (
                            <option key={entry.entry_id} value={entry.entry_id}>
                              #{entry.number} {entry.driver_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t('handicaps.round')}
                        <select name="round_id" required defaultValue={data.data?.next_round_id ?? ''}>
                          {rounds.map((round) => (
                            <option key={round.id} value={round.id}>
                              {t('season.roundLabel', { number: round.number })} · {round.track_name}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <div className="field-row">
                      <label>
                        {t('handicaps.ballast')}
                        <input name="ballast_kg" type="number" min={0} max={rules.ballast_cap} required />
                      </label>
                      <label>
                        {t('handicaps.restrictor')}
                        <input name="restrictor_pct" type="number" min={0} max={rules.restrictor_cap} required />
                      </label>
                    </div>
                    <label>
                      {t('handicaps.mode')}
                      <select name="mode" defaultValue="temporary">
                        <option value="temporary">{t('handicaps.modes.temporary')}</option>
                        <option value="persistent">{t('handicaps.modes.persistent')}</option>
                      </select>
                    </label>
                    <label>
                      {t('handicaps.reason')}
                      <input name="reason" required maxLength={500} />
                    </label>
                  </ActionForm>
                ),
              },
            ]}
          />
        )}
      </div>
      <p className="muted">
        {t('handicaps.rules', {
          ballast: rules.ballast_steps.join('/'),
          restrictor: rules.restrictor_steps.join('/'),
          reduction_kg: rules.ballast_reduction,
          reduction_pct: rules.restrictor_reduction,
          cap_kg: rules.ballast_cap,
          cap_pct: rules.restrictor_cap,
        })}
      </p>
      <div className="table-wrap">
        <table className="handicaps">
          <thead>
            <tr>
              <th scope="col">{t('handicaps.driver')}</th>
              {raced.map((step) => (
                <th scope="col" key={step.round_id}>
                  R{step.round_number}
                </th>
              ))}
              <th scope="col" className="next">
                {next_round_number ? t('handicaps.next', { number: next_round_number }) : t('handicaps.noNext')}
              </th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.entry_id}>
                <td>
                  <details>
                    <summary>
                      #{entry.number} {entry.driver_name}
                    </summary>
                    <ul className="explain" aria-label={t('handicaps.explain', { name: entry.driver_name })}>
                      {entry.rounds.map((step) => (
                        <li key={step.round_id}>
                          {stepLine(t, step)}
                          {step.capped && <span className="badge">{t('handicaps.capped')}</span>}
                          {step.adjustment_reason && (
                            <span className="muted"> · {t('handicaps.adjusted', { reason: step.adjustment_reason })}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                </td>
                {entry.rounds.map((step) => {
                  const differs =
                    step.used_kg !== null &&
                    step.used_kg !== undefined &&
                    (step.used_kg !== step.before_kg || step.used_pct !== step.before_pct)
                  return (
                    <td
                      key={step.round_id}
                      className={differs ? 'differs' : undefined}
                      title={differs ? t('handicaps.usedDiffers', { used: value(step.used_kg!, step.used_pct!) }) : undefined}
                    >
                      {differs ? value(step.used_kg!, step.used_pct!) : value(step.before_kg, step.before_pct)}
                    </td>
                  )
                })}
                <td className="next" title={entry.next_adjustment_reason ?? undefined}>
                  <strong>{value(entry.next_kg, entry.next_pct)}</strong>
                  {entry.next_adjustment_reason && ' *'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

    </>
  )
}
