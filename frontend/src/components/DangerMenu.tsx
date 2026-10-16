import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ConfirmDelete, type DeleteTarget } from './ConfirmDelete'
import { Icon } from './Icon'
import { RowMenu, type MenuItem } from './RowMenu'

/** A "more" menu with a red delete item at its end, and the confirmation of the delete.
 * items: the other actions of the menu, before the delete. */
export function DangerMenu({
  target,
  onDeleted,
  items = [],
  label,
  wide = false,
}: {
  target: DeleteTarget
  onDeleted: () => void
  items?: MenuItem[]
  // The name of the menu button. Without it: "Más opciones de <name>".
  label?: string
  // At the top of a page: a button with the word "Opciones". Else the "more" icon.
  wide?: boolean
}) {
  const { t } = useTranslation()
  const [deleting, setDeleting] = useState<DeleteTarget | null>(null)
  return (
    <span className={wide ? 'danger-menu wide' : 'danger-menu'}>
      <RowMenu
        trigger={
          wide ? (
            <>
              <Icon name="more" small />
              {t('deletion.options')}
            </>
          ) : undefined
        }
        label={label ?? t('deletion.menu', { name: target.name })}
        items={[...items, { label: t(`deletion.delete.${target.kind}`), danger: true, onSelect: () => setDeleting(target) }]}
      />
      <ConfirmDelete target={deleting} onClose={() => setDeleting(null)} onDeleted={onDeleted} />
    </span>
  )
}
