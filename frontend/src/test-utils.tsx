import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { vi } from 'vitest'
import type { Me } from './api/client'
import type { Mode } from './session'
import { SessionProvider } from './SessionProvider'

export const ADMIN: Me = { id: 1, username: 'santi', language: 'es', is_admin: true, can_admin: true }
export const DRIVER: Me = { id: 2, username: 'racer', language: 'es', is_admin: false, can_admin: false }

export function json(status: number, body?: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type Handler = (request: Request) => Response | Promise<Response>

/** Replace fetch. Each key is "METHOD /path". The mock returns the calls it saw. */
export function mockApi(routes: Record<string, Handler>) {
  const calls: { key: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const request = input as Request
    const key = `${request.method} ${new URL(request.url).pathname}`
    const text = await request.clone().text()
    calls.push({ key, body: text ? JSON.parse(text) : undefined })
    const handler = routes[key]
    if (!handler) throw new Error(`No mock for ${key}`)
    return handler(request)
  })
  return calls
}

/** Render one page at a URL, with a signed-in user. An admin starts in the admin mode. */
export function renderPage(
  page: ReactElement,
  { path, url, me = ADMIN, mode }: { path: string; url: string; me?: Me; mode?: Mode },
) {
  localStorage.setItem('paddock.mode', mode ?? (me.can_admin ? 'admin' : 'driver'))
  return render(
    <SessionProvider me={me}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path={path} element={page} />
        </Routes>
      </MemoryRouter>
    </SessionProvider>,
  )
}
