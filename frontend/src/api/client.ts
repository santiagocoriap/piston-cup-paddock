import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from './schema'

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export function readCookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((part) => part.startsWith(`${name}=`))
    ?.slice(name.length + 1)
}

// Django needs the CSRF token in a header for each request that changes data.
const csrf: Middleware = {
  onRequest({ request }) {
    const token = readCookie('csrftoken')
    if (token && UNSAFE_METHODS.has(request.method)) {
      request.headers.set('X-CSRFToken', token)
    }
    return request
  },
}

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: 'same-origin',
  // Look up fetch on each call, so tests can replace it.
  fetch: (request) => globalThis.fetch(request),
})
api.use(csrf)

export type Me = paths['/api/auth/me']['get']['responses'][200]['content']['application/json']
