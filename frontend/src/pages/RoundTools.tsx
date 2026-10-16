import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { Dialog } from '../components/Dialog'
import { errorMessage } from '../lib/errors'
import { useLoad } from '../lib/useLoad'
import { drawConditions } from '../lib/drawConditions'
import { DangerMenu } from '../components/DangerMenu'
import { RoundSettingsForm } from './RoundSettingsForm'

type RoundOut = components['schemas']['RoundOut']

/** Admin tools for one calendar round, in a row menu: cancel or restore it, replace its track,
 * and draw its conditions. */
export function RoundTools({ round, onChange }: { round: RoundOut; onChange: () => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [settings, setSettings] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const tracks = useLoad(() => (open ? api.GET('/api/catalog/tracks') : Promise.resolve({ data: undefined })), [open])
  const title = t('roundTools.replaceTitle', { number: round.number })

  async function cancelOrRestore() {
    const reason = window.prompt(t(round.cancelled ? 'roundTools.restoreReason' : 'roundTools.cancelReason'))
    if (!reason) return
    const path = { params: { path: { round_id: round.id } }, body: { reason } }
    const { error } = round.cancelled
      ? await api.POST('/api/rounds/{round_id}/restore', path)
      : await api.POST('/api/rounds/{round_id}/cancel', path)
    if (error) setError(errorMessage(t, error))
    else onChange()
  }

  return (
    <span className="round-tools">
      <DangerMenu
        target={{ kind: 'round', id: round.id, name: `${t('season.roundLabel', { number: round.number })} · ${round.track_name}` }}
        onDeleted={onChange}
        label={t('roundTools.menu', { number: round.number })}
        items={[
          { label: t('roundTools.settings'), onSelect: () => setSettings(true) },
          { label: t(round.cancelled ? 'roundTools.restore' : 'roundTools.cancel'), onSelect: cancelOrRestore },
          { label: t('roundTools.replace'), onSelect: () => setOpen(true) },
          {
            label: t('draw.button'),
            onSelect: async () => {
              const problem = await drawConditions(round.id, t)
              if (problem) setError(problem)
              else onChange()
            },
          },
        ]}
      />
      <Dialog open={settings} title={t('roundTools.settings')} onClose={() => setSettings(false)}>
        {settings && <RoundSettingsForm round={round} onChange={onChange} onDone={() => setSettings(false)} />}
      </Dialog>
      <Dialog open={open} title={title} onClose={() => setOpen(false)}>
        {open && (
          <ActionForm
            title={title}
            submitLabel={t('common.save')}
            onDone={() => setOpen(false)}
            onSubmit={async (form) => {
              const { error } = await api.POST('/api/rounds/{round_id}/replace-track', {
                params: { path: { round_id: round.id } },
                body: { track_layout_id: Number(form.get('track_layout_id')), reason: String(form.get('reason')) },
              })
              if (!error) onChange()
              return error
            }}
          >
            <label>
              {t('roundTools.newTrack')}
              <select name="track_layout_id" required>
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
              {t('roundTools.reason')}
              <input name="reason" required maxLength={500} />
            </label>
          </ActionForm>
        )}
      </Dialog>
      {error && (
        <span role="alert" className="error">
          {error}
        </span>
      )}
    </span>
  )
}

/** A new season with the entries, rules, and fixed tracks of this one. */
export function CloneSeasonForm({ seasonId, onDone }: { seasonId: number; onDone?: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <div className="forms">
      <ActionForm
        title={t('roundTools.cloneTitle')}
        submitLabel={t('roundTools.clone')}
        onSubmit={async (form) => {
          const { data, error } = await api.POST('/api/seasons/{season_id}/clone', {
            params: { path: { season_id: seasonId } },
            body: { name: String(form.get('name')) },
          })
          if (data) {
            onDone?.()
            navigate(`/seasons/${data.id}`)
          }
          return error
        }}
      >
        <p className="muted">{t('roundTools.cloneHelp')}</p>
        <label>
          {t('roundTools.cloneName')}
          <input name="name" required maxLength={100} />
        </label>
      </ActionForm>
    </div>
  )
}
