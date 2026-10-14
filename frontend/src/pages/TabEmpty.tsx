import type { ReactNode } from 'react'
import { EmptyState } from '../components/EmptyState'
import type { IconName } from '../components/Icon'

/** A round tab without data. It says why the tab is empty, so the page does not look broken. */
export function TabEmpty({
  heading,
  icon,
  title,
  text,
  children,
}: {
  heading: string
  icon: IconName
  title: string
  text: string
  children?: ReactNode
}) {
  return (
    <section aria-label={heading}>
      <h2>{heading}</h2>
      <EmptyState icon={icon} title={title} text={text}>
        {children}
      </EmptyState>
    </section>
  )
}
