import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../../api/client'
import type { components } from '../../api/schema'
import { ActionForm } from '../../components/ActionForm'
import { Dialog } from '../../components/Dialog'
import { EmptyState } from '../../components/EmptyState'
import { Icon } from '../../components/Icon'
import { Loading } from '../../components/Layout'
import { errorMessage } from '../../lib/errors'
import { useLoad } from '../../lib/useLoad'
import { Breadcrumbs } from '../../components/Breadcrumbs'

type League = components['schemas']['LeagueOut']

export function LeaguesPage() {
  const { t } = useTranslation()
  const leagues = useLoad(() => api.GET('/api/leagues'), [])
  const [adding, setAdding] = useState(false)

  const addButton = (
    <button type="button" onClick={() => setAdding(true)}>
      <Icon name="plus" small />
      {t('leagues.newLeague')}
    </button>
  )

  return (
    <section>
      <Breadcrumbs items={[{ label: t('nav.leagues') }]} />
      <header className="page-head">
        <div>
          <h1>{t('leagues.title')}</h1>
          <p className="muted">{t('leagues.help')}</p>
        </div>
        {leagues.data && leagues.data.length > 0 && <div className="page-actions">{addButton}</div>}
      </header>
      {!leagues.data ? (
        <Loading failed={leagues.failed} />
      ) : leagues.data.length === 0 ? (
        <EmptyState icon="trophy" title={t('leagues.empty')} text={t('leagues.emptyText')}>
          {addButton}
        </EmptyState>
      ) : (
        <div className="league-list">
          {leagues.data.map((league) => (
            <LeagueCard key={league.id} league={league} onChange={leagues.reload} />
          ))}
        </div>
      )}
      <Dialog open={adding} title={t('leagues.newLeague')} onClose={() => setAdding(false)}>
        <ActionForm
          title={t('leagues.newLeague')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/leagues', {
              body: { name: String(form.get('name')) },
            })
            if (!error) {
              setAdding(false)
              leagues.reload()
            }
            return error
          }}
        >
          <label>
            {t('common.name')}
            <input name="name" required maxLength={100} />
          </label>
        </ActionForm>
      </Dialog>
    </section>
  )
}

/** One league as a tree node: the league opens and closes, its championships are the leaves. */
function LeagueCard({ league, onChange }: { league: League; onChange: () => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(true)
  const listId = useId()
  const seasons = league.championships.reduce((sum, c) => sum + c.season_count, 0)
  return (
    <article className="card league" aria-label={league.name}>
      <button type="button" className="league-toggle" aria-expanded={open} aria-controls={listId} onClick={() => setOpen(!open)}>
        <span className="league-chevron">
          <Icon name="chevron" small />
        </span>
        <span className="league-name">{league.name}</span>
        <span className="league-meta">
          {t('leagues.championshipCount', { count: league.championships.length })} ·{' '}
          {t('leagues.seasonCount', { count: seasons })}
        </span>
      </button>
      <p className="league-zone muted">
        <Icon name="clock" small />
        {t('leagues.timezone', { zone: league.timezone })}
      </p>
      <div id={listId} hidden={!open}>
        {league.championships.length === 0 && <p className="muted league-none">{t('leagues.noChampionships')}</p>}
        <ul className="league-tree">
          {league.championships.map((championship) => (
            <li key={championship.id}>
              <Icon name="flag" small />
              <span className="league-leaf-name">{championship.name}</span>
              <span className="muted">{t('leagues.seasonCount', { count: championship.season_count })}</span>
              <Link className="small-link" to={`/championships/${championship.id}`}>
                {t('leagues.open')}
                <Icon name="arrow" small />
              </Link>
            </li>
          ))}
        </ul>
        <AddChampionship league={league} onCreated={onChange} />
      </div>
    </article>
  )
}

/** A dashed "add" row that opens into a one-field form. */
function AddChampionship({ league, onCreated }: { league: League; onCreated: () => void }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = String(new FormData(event.currentTarget).get('name')).trim()
    setBusy(true)
    setError(null)
    const { error: apiError } = await api.POST('/api/leagues/{league_id}/championships', {
      params: { path: { league_id: league.id } },
      body: { name },
    })
    setBusy(false)
    if (apiError) {
      setError(errorMessage(t, apiError))
      return
    }
    setEditing(false)
    setCreated(name)
    onCreated()
  }

  return (
    <div className="league-add">
      {created && (
        <p role="status" className="league-created">
          <Icon name="check" small />
          {t('leagues.created', { name: created })}
        </p>
      )}
      {editing ? (
        <form className="league-add-form" onSubmit={submit} aria-label={`${t('leagues.newChampionship')}: ${league.name}`}>
          <input name="name" required maxLength={100} aria-label={t('leagues.championshipName')} placeholder={t('leagues.championshipName')} autoFocus />
          <button type="submit" disabled={busy}>
            {t('common.create')}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setEditing(false)
              setError(null)
            }}
          >
            {t('common.cancel')}
          </button>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
        </form>
      ) : (
        <button
          type="button"
          className="add-row"
          onClick={() => {
            setEditing(true)
            setCreated(null)
          }}
        >
          <Icon name="plus" small />
          {t('leagues.newChampionship')}
        </button>
      )}
    </div>
  )
}
