import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../../api/client'
import { ActionForm } from '../../components/ActionForm'
import { Loading } from '../../components/Layout'
import { errorMessage } from '../../lib/errors'
import { useLoad } from '../../lib/useLoad'

export function DriversPage() {
  const { t } = useTranslation()
  const drivers = useLoad(() => api.GET('/api/drivers'), [])
  const users = useLoad(() => api.GET('/api/users'), [])
  const [linkError, setLinkError] = useState<string | null>(null)

  async function link(driverId: number, value: string) {
    setLinkError(null)
    const { error } = await api.POST('/api/drivers/{driver_id}/link', {
      params: { path: { driver_id: driverId } },
      body: { user_id: value ? Number(value) : null },
    })
    if (error) setLinkError(errorMessage(t, error))
    drivers.reload()
  }

  if (!drivers.data) return <Loading failed={drivers.failed} />
  return (
    <section>
      <h1>{t('drivers.title')}</h1>
      {drivers.data.length === 0 && <p>{t('drivers.empty')}</p>}
      {linkError && (
        <p role="alert" className="error">
          {linkError}
        </p>
      )}
      {drivers.data.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('drivers.displayName')}</th>
                <th scope="col">Steam GUID</th>
                <th scope="col">{t('drivers.account')}</th>
                <th scope="col">{t('drivers.careerPoints')}</th>
              </tr>
            </thead>
            <tbody>
              {drivers.data.map((driver) => (
                <tr key={driver.id}>
                  <td>{driver.display_name}</td>
                  <td className="mono">{driver.steam_guid ?? '—'}</td>
                  <td>
                    <select
                      aria-label={`${t('drivers.account')} ${driver.display_name}`}
                      value={driver.user_id ?? ''}
                      onChange={(event) => link(driver.id, event.target.value)}
                    >
                      <option value="">{t('drivers.noAccount')}</option>
                      {users.data?.map((user) => (
                        <option key={user.id} value={user.id}>
                          {user.username}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>{driver.career_points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="forms">
        <ActionForm
          title={t('drivers.newDriver')}
          submitLabel={t('common.create')}
          onSubmit={async (form) => {
            const guid = String(form.get('steam_guid') ?? '').trim()
            const { error } = await api.POST('/api/drivers', {
              body: { display_name: String(form.get('display_name')), steam_guid: guid || null },
            })
            if (!error) drivers.reload()
            return error
          }}
        >
          <label>
            {t('drivers.displayName')}
            <input name="display_name" required maxLength={100} />
          </label>
          <label>
            {t('drivers.steamGuid')}
            <input name="steam_guid" inputMode="numeric" pattern="\d{17}" />
          </label>
        </ActionForm>
        {drivers.data && drivers.data.length > 1 && (
          <ActionForm
            title={t('drivers.merge')}
            submitLabel={t('drivers.mergeButton')}
            onSubmit={async (form) => {
              if (!window.confirm(t('drivers.confirmMerge'))) return undefined
              const { error } = await api.POST('/api/drivers/{driver_id}/merge', {
                params: { path: { driver_id: Number(form.get('old_id')) } },
                body: { into_id: Number(form.get('into_id')), reason: String(form.get('reason')) },
              })
              if (!error) drivers.reload()
              return error
            }}
          >
            <p className="muted">{t('drivers.mergeHelp')}</p>
            <label>
              {t('drivers.mergeOld')}
              <select name="old_id" required>
                {drivers.data.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t('drivers.mergeInto')}
              <select name="into_id" required>
                {drivers.data.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t('drivers.mergeReason')}
              <input name="reason" required maxLength={500} />
            </label>
          </ActionForm>
        )}
      </div>
    </section>
  )
}
