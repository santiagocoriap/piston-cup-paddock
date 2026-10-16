import { initials } from '../lib/initials'

/** The picture of a person, or the initials when there is no picture. The name is next to
 * it on the page, so the picture is hidden from screen readers. */
export function Avatar({ name, url, className = '' }: { name: string; url?: string | null; className?: string }) {
  return (
    <span className={`avatar ${className}`.trim()} aria-hidden="true">
      {url ? <img src={url} alt="" loading="lazy" /> : initials(name)}
    </span>
  )
}
