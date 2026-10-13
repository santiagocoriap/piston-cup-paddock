import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { api, readCookie } from '../api/client'
import type { components } from '../api/schema'
import { ActionForm } from '../components/ActionForm'
import { errorMessage } from '../lib/errors'
import { useMe } from '../session'

type Protest = components['schemas']['ProtestOut']

/** Evidence, the appeal, and the appeal decision of one protest. */
export function ProtestExtras({
  protest,
  canDecide,
  onChange,
}: {
  protest: Protest
  canDecide: boolean
  onChange: () => void
}) {
  const { t } = useTranslation()
  const me = useMe()
  const [error, setError] = useState<string | null>(null)
  const isAuthor = protest.submitted_by === me.username
  const evidenceOpen = protest.status === 'open' || protest.appeal_status === 'open'
  const evidence = protest.evidence ?? []

  async function addEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const element = event.currentTarget
    // A file goes with a plain fetch. The typed client sends JSON.
    const response = await fetch(`/api/protests/${protest.id}/evidence`, {
      method: 'POST',
      body: new FormData(element),
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': readCookie('csrftoken') ?? '' },
    }).catch(() => null)
    const body = response ? await response.json().catch(() => null) : null
    if (!response?.ok) setError(errorMessage(t, body))
    else {
      element.reset()
      onChange()
    }
  }

  return (
    <>
      {evidence.length > 0 && (
        <ul className="evidence">
          {evidence.map((item) => (
            <li key={item.id}>
              {item.url ? (
                <a href={item.url} target="_blank" rel="noreferrer noopener">
                  {item.url}
                </a>
              ) : (
                <a href={`/api/protest-evidence/${item.id}`} target="_blank" rel="noreferrer">
                  {item.filename}
                </a>
              )}
              {item.uploaded_by && <span className="muted"> · {item.uploaded_by}</span>}
            </li>
          ))}
        </ul>
      )}
      {evidenceOpen && (isAuthor || canDecide) && (
        <form className="upload" onSubmit={addEvidence} aria-label={t('protestExtras.addEvidence')}>
          <label>
            {t('protestExtras.link')}
            <input name="url" type="url" placeholder="https://" />
          </label>
          <label>
            {t('protestExtras.file')}
            <input name="file" type="file" accept="image/*,video/*" />
          </label>
          <button type="submit">{t('protestExtras.addEvidence')}</button>
        </form>
      )}
      {protest.appeal_status && (
        <p className={protest.appeal_status === 'open' ? 'warning' : 'reason'}>
          {t(`protestExtras.appeal.${protest.appeal_status}`)}: {protest.appeal_reason}
          {protest.appeal_decision && ` — ${protest.appeal_decided_by}: ${protest.appeal_decision}`}
        </p>
      )}
      {protest.can_appeal && (
        <ActionForm
          title={t('protestExtras.appealTitle')}
          submitLabel={t('protestExtras.appealButton')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/protests/{protest_id}/appeal', {
              params: { path: { protest_id: protest.id } },
              body: { reason: String(form.get('reason')) },
            })
            if (!error) onChange()
            return error
          }}
        >
          <label>
            {t('protestExtras.appealReason')}
            <textarea name="reason" rows={2} required maxLength={2000} />
          </label>
        </ActionForm>
      )}
      {canDecide && protest.appeal_status === 'open' && (
        <ActionForm
          title={t('protestExtras.decideAppeal')}
          submitLabel={t('common.save')}
          onSubmit={async (form) => {
            const { error } = await api.POST('/api/protests/{protest_id}/appeal-decision', {
              params: { path: { protest_id: protest.id } },
              body: {
                outcome: form.get('outcome') as 'upheld' | 'dismissed',
                decision: String(form.get('decision')),
              },
            })
            if (!error) onChange()
            return error
          }}
        >
          <label>
            {t('protestExtras.outcome')}
            <select name="outcome" defaultValue="dismissed">
              <option value="upheld">{t('protestExtras.appeal.upheld')}</option>
              <option value="dismissed">{t('protestExtras.appeal.dismissed')}</option>
            </select>
          </label>
          <label>
            {t('protestExtras.decision')}
            <textarea name="decision" rows={2} required maxLength={2000} />
          </label>
          <p className="muted">{t('protestExtras.appealHelp')}</p>
        </ActionForm>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </>
  )
}
