import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { DualPicker, type PickItem } from '../components/DualPicker'
import { errorMessage } from '../lib/errors'
import { useLoad } from '../lib/useLoad'

type Ballot = components['schemas']['BallotDetail']

/** The options of a draft ballot as one checklist: every layout (or car class) of the catalog.
 * Tick to add, untick to remove, "Elegir todas" for every one that can go in. A layout that
 * cannot go in shows in grey with the reason. One "Guardar" saves the list. */
export function BallotOptionPicker({ ballot, onDone }: { ballot: Ballot; onDone: () => void }) {
  const { t } = useTranslation()
  const path = { ballot_id: ballot.id }
  const candidates = useLoad(() => api.GET('/api/ballots/{ballot_id}/candidates', { params: { path } }), [ballot.id])
  const [chosen, setChosen] = useState<number[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (candidates.data && chosen === null) {
      setChosen(candidates.data.filter((c) => c.status === 'added').map((c) => c.id))
    }
  }, [candidates.data, chosen])

  const isTrack = ballot.kind === 'track'
  const items = useMemo<PickItem[]>(
    () =>
      (candidates.data ?? []).map((c) => ({
        id: c.id,
        title: c.label || c.group,
        group: c.group || undefined,
        image: c.image_url,
        kind: isTrack ? 'track' : 'car',
        blocked: c.status === 'ok' || c.status === 'added' ? undefined : t(`optionPicker.why.${c.status}`),
      })),
    [candidates.data, isTrack, t],
  )

  async function save() {
    if (!chosen) return
    setError(null)
    setBusy(true)
    const { error } = await api.PUT('/api/ballots/{ballot_id}/options', {
      params: { path },
      body: { ids: chosen },
    })
    setBusy(false)
    if (error) setError(errorMessage(t, error))
    else onDone()
  }

  return (
    <div className="modal-body option-picker">
      <h3>{t('optionPicker.title')}</h3>
      <p className="muted">{t(isTrack ? 'optionPicker.helpTracks' : 'optionPicker.helpClasses')}</p>
      {chosen && (
        <DualPicker items={items} value={chosen} onChange={setChosen} searchLabel={t('optionPicker.search')} />
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="settings-actions">
        <button type="button" onClick={save} disabled={busy || chosen === null}>
          {busy && <span className="spinner" aria-hidden="true" />}
          {t('optionPicker.save', { count: chosen?.length ?? 0 })}
        </button>
      </div>
    </div>
  )
}
