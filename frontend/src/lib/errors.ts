import type { TFunction } from 'i18next'

/** Turn an API error body into a message in the user's language. */
export function errorMessage(t: TFunction, error: unknown): string {
  const detail =
    typeof error === 'object' && error !== null && 'detail' in error ? error.detail : undefined
  if (typeof detail === 'string' && t(`errors.${detail}`, { defaultValue: '' })) {
    return t(`errors.${detail}`)
  }
  return t('errors.generic')
}
