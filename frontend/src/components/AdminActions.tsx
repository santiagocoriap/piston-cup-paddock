import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog } from './Dialog'
import { Icon } from './Icon'
import { RowMenu } from './RowMenu'

// The content gets "close", so a form can close its dialog after it saves.
export type AdminAction = { id: string; label: string; content: (close: () => void) => ReactNode }

/** The admin actions of a section. One action is a button. More actions are a menu.
 * Each action opens its form in a dialog, so the section reads the same for a driver. */
export function AdminActions({ actions }: { actions: AdminAction[] }) {
  const { t } = useTranslation()
  const [openId, setOpenId] = useState<string | null>(null)
  const current = actions.find((action) => action.id === openId)
  if (actions.length === 0) return null
  const close = () => setOpenId(null)
  return (
    <div className="admin-actions">
      {actions.length === 1 ? (
        <button type="button" className="secondary small" onClick={() => setOpenId(actions[0].id)}>
          <Icon name="shield" small />
          {actions[0].label}
        </button>
      ) : (
        <RowMenu
          label={t('seasonAdmin.manage')}
          trigger={
            <>
              <Icon name="shield" small />
              {t('seasonAdmin.manage')}
              <Icon name="chevron" small />
            </>
          }
          items={actions.map((action) => ({ label: action.label, onSelect: () => setOpenId(action.id) }))}
        />
      )}
      <Dialog open={current !== undefined} title={current?.label ?? ''} onClose={close}>
        {current && <div className="admin-dialog">{current.content(close)}</div>}
      </Dialog>
    </div>
  )
}
