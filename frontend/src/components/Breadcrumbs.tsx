import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Icon } from './Icon'

export type Crumb = { label: string; to?: string }

/** The path from Inicio to this page. The last item is this page and has no link. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useTranslation()
  const all: Crumb[] = [{ label: t('nav.home'), to: '/' }, ...items]
  return (
    <nav className="breadcrumbs" aria-label={t('nav.breadcrumbs')}>
      <ol>
        {all.map((item, index) => {
          const last = index === all.length - 1
          return (
            <li key={`${index}-${item.label}`}>
              {index > 0 && (
                <span className="crumb-separator" aria-hidden="true">
                  <Icon name="chevron" small />
                </span>
              )}
              {last ? (
                <span aria-current="page">{item.label}</span>
              ) : item.to ? (
                <Link to={item.to}>
                  {index === 0 && <Icon name="home" small />}
                  {item.label}
                </Link>
              ) : (
                <span>{item.label}</span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
