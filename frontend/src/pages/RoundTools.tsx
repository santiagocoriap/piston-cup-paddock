import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { errorMessage } from '../lib/errors'
import { useLoad } from '../lib/useLoad'

type RoundOut = components['schemas']['RoundOut']

/** Admin tools for one calendar round: cancel or restore it, and replace its track. */
export function RoundTools({ round, onChange }: { round: RoundOut; onChange: () => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const tracks = useLoad(() => (open ? api.GET('/api/catalog/tracks') : Promise.resolve({ data: undefined })), [open])

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
      <button type="button" className="secondary small" onClick={cancelOrRestore}>
        {t(round.cancelled ? 'roundTools.restore' : 'roundTools.cancel')}
      </button>{' '}
      <button type="button" className="secondary small" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {t('roundTools.replace')}
      </button>
      {open && (
        <ActionForm
          title={t('roundTools.replaceTitle', { number: round.number })}
          submitLabel={t('common.save')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/rounds/{round_id}/replace-track', {
              params: { path: { round_id: round.id } },
              body: { track_layout_id: Number(form.get('track_layout_id')), reason: String(form.get('reason')) },
            })
            if (!error) {
              setOpen(false)
              onChange()
            }
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
      {error && (
        <span role="alert" className="error">
          {' '}
          {error}
        </span>
      )}
    </span>
  )
}

/** A new season with the entries, rules, and fixed tracks of this one. */
export function CloneSeasonForm({ seasonId }: { seasonId: number }) {
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
          if (data) navigate(`/seasons/${data.id}`)
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
