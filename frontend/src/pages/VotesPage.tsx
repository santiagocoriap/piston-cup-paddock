import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { components } from '../api/schema'
import { Breadcrumbs } from '../components/Breadcrumbs'
import { EmptyState } from '../components/EmptyState'
import { Icon } from '../components/Icon'
import { Loading } from '../components/Layout'
import { formatDateTime } from '../lib/format'
import { useLoad } from '../lib/useLoad'

type MyBallot = components['schemas']['MyBallotOut']

/** The votes of the user: the open ones first, with a mark on the ones that wait for a vote. */
export function VotesPage() {
  const { t, i18n } = useTranslation()
  const ballots = useLoad(() => api.GET('/api/me/ballots'), [])
  if (!ballots.data) return <Loading failed={ballots.failed} />
  const open = ballots.data.filter((b) => b.status === 'open')
  const done = ballots.data.filter((b) => b.status !== 'open')

  const row = (ballot: MyBallot) => {
    const waiting = ballot.status === 'open' && !ballot.voted
    return (
      <li key={ballot.id} className={waiting ? 'vote-row waiting' : 'vote-row'}>
        <Icon name={waiting ? 'alert' : ballot.status === 'open' ? 'check' : 'flag'} small />
        <div className="vote-row-main">
          <Link to={`/ballots/${ballot.id}`}>{ballot.title}</Link>
          <span className="muted">
            {ballot.championship} · {ballot.season}
            {ballot.status === 'open' && ballot.closes_at && (
              <> · {t('votes.closes', { date: formatDateTime(ballot.closes_at, i18n.language) })}</>
            )}
            {ballot.winners.length > 0 && <> · {t('voting.winners', { list: ballot.winners.join(', ') })}</>}
          </span>
        </div>
        {ballot.status === 'open' ? (
          waiting ? (
            <Link className="button-link" to={`/ballots/${ballot.id}`}>
              {t('votes.vote')}
            </Link>
          ) : (
            <span className="badge">{t('votes.voted')}</span>
          )
        ) : (
          <span className={`badge ballot-${ballot.status}`}>{t(`voting.status.${ballot.status}`)}</span>
        )}
      </li>
    )
  }

  return (
    <section>
      <Breadcrumbs items={[{ label: t('nav.votes') }]} />
      <header className="page-head">
        <div>
          <h1>{t('nav.votes')}</h1>
          <p className="muted">{t('votes.help')}</p>
        </div>
      </header>
      {ballots.data.length === 0 ? (
        <EmptyState icon="check" title={t('votes.emptyTitle')} text={t('votes.emptyText')} />
      ) : (
        <>
          {open.length > 0 && (
            <>
              <h2>{t('votes.open')}</h2>
              <ul className="vote-list">{open.map(row)}</ul>
            </>
          )}
          {done.length > 0 && (
            <>
              <h2>{t('votes.done')}</h2>
              <ul className="vote-list">{done.map(row)}</ul>
            </>
          )}
        </>
      )}
    </section>
  )
}
