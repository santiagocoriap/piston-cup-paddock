import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { components } from '../api/schema'
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
  const [chosen, setChosen] = useState<Set<number> | null>(null)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (candidates.data && chosen === null) {
      setChosen(new Set(candidates.data.filter((c) => c.status === 'added').map((c) => c.id)))
    }
  }, [candidates.data, chosen])

  const shown = useMemo(() => {
    const words = query.trim().toLowerCase()
    return (candidates.data ?? []).filter(
      (c) => !words || `${c.group} ${c.label}`.toLowerCase().includes(words),
    )
  }, [candidates.data, query])
  const available = shown.filter((c) => c.status === 'ok' || c.status === 'added')
  const allChosen = available.length > 0 && available.every((c) => chosen?.has(c.id))

  function toggle(id: number) {
    setChosen((old) => {
      const next = new Set(old)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    setChosen((old) => {
      const next = new Set(old)
      for (const c of available) {
        if (allChosen) next.delete(c.id)
        else next.add(c.id)
      }
      return next
    })
  }

  async function save() {
    if (!chosen) return
    setError(null)
    setBusy(true)
    const { error } = await api.PUT('/api/ballots/{ballot_id}/options', {
      params: { path },
      body: { ids: [...chosen] },
    })
    setBusy(false)
    if (error) setError(errorMessage(t, error))
    else onDone()
  }

  const isTrack = ballot.kind === 'track'
  return (
    <div className="modal-body option-picker">
      <h3>{t('optionPicker.title')}</h3>
      <p className="muted">{t(isTrack ? 'optionPicker.helpTracks' : 'optionPicker.helpClasses')}</p>
      <div className="option-picker-filters">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('optionPicker.search')}
          aria-label={t('optionPicker.search')}
        />
        <label className="check">
          <input type="checkbox" checked={allChosen} onChange={toggleAll} disabled={available.length === 0} />
          {t('optionPicker.all', { count: available.length })}
        </label>
      </div>
      <ul className="option-picker-list">
        {shown.map((c) => {
          const blocked = c.status !== 'ok' && c.status !== 'added'
          return (
            <li key={c.id} className={blocked ? 'blocked' : chosen?.has(c.id) ? 'on' : undefined}>
              <label className="check">
                <input type="checkbox" checked={!blocked && !!chosen?.has(c.id)} disabled={blocked} onChange={() => toggle(c.id)} />
                {c.image_url ? <img src={c.image_url} alt="" loading="lazy" /> : <span className="option-picker-thumb" aria-hidden="true" />}
                <span className="option-picker-name">
                  <b>{c.group || c.label}</b>
                  {c.group && <span className="muted">{c.label}</span>}
                  {blocked && <span className="option-picker-why">{t(`optionPicker.why.${c.status}`)}</span>}
                </span>
              </label>
            </li>
          )
        })}
        {candidates.data && shown.length === 0 && <li className="muted">{t('optionPicker.none')}</li>}
      </ul>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="settings-actions">
        <button type="button" onClick={save} disabled={busy || chosen === null}>
          {busy && <span className="spinner" aria-hidden="true" />}
          {t('optionPicker.save', { count: chosen?.size ?? 0 })}
        </button>
      </div>
    </div>
  )
}
