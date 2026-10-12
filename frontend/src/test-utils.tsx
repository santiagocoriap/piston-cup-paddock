import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { vi } from 'vitest'
import type { Me } from './api/client'
import { SessionContext } from './session'

export const ADMIN: Me = { id: 1, username: 'santi', language: 'es', is_admin: true }
export const DRIVER: Me = { id: 2, username: 'racer', language: 'es', is_admin: false }

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

/** Render one page at a URL, with a signed-in user. */
export function renderPage(page: ReactElement, { path, url, me = ADMIN }: { path: string; url: string; me?: Me }) {
  return render(
    <SessionContext.Provider value={me}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path={path} element={page} />
        </Routes>
      </MemoryRouter>
    </SessionContext.Provider>,
  )
}
