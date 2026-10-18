import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { vi } from 'vitest'
import type { Me } from './api/client'
import type { components } from './api/schema'
import type { Mode } from './session'
import { SessionProvider } from './SessionProvider'

export const ADMIN: Me = { id: 1, username: 'santi', language: 'es', timezone: '', is_admin: true, is_platform_admin: true, can_admin: true, can_manage: true }
export const DRIVER: Me = { id: 2, username: 'racer', language: 'es', timezone: '', is_admin: false, is_platform_admin: false, can_admin: false, can_manage: false }

type Car = components['schemas']['CarOut']

/** A catalog car with every field empty, plus the given fields. */
export function carOf(fields: Partial<Car> & Pick<Car, 'id' | 'key' | 'name'>): Car {
  return {
    has_preview: false, has_badge: false, brand: '', author: '', game_class: '', country: '', year: null,
    power_hp: null, torque_nm: null, weight_kg: null, top_speed_kmh: null, acceleration: '', power_to_weight: '',
    specs_text: {}, version: '', url: '', description: '', tags: [], power_curve: [], torque_curve: [],
    source: 'mod', source_url: '', has_data: false, data_error: '', skins: [], tyres: [],
    ...fields,
  }
}

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
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    // The typed client sends a Request. A file upload sends a URL string and options.
    const request = input instanceof Request ? input : null
    const method = request?.method ?? init?.method ?? 'GET'
    const url = request?.url ?? new URL(String(input), 'http://localhost').toString()
    const key = `${method} ${new URL(url).pathname}`
    let body: unknown = undefined
    if (request) {
      const text = await request.clone().text()
      try {
        body = text ? JSON.parse(text) : undefined
      } catch {
        body = text
      }
    } else if (init?.body instanceof FormData) {
      body = Object.fromEntries([...init.body.keys()].map((name) => [name, '[form field]']))
    }
    calls.push({ key, body })
    const handler = routes[key]
    if (!handler) throw new Error(`No mock for ${key}`)
    return handler(request ?? new Request(url, { method }))
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
    <SessionProvider me={me} onMeChange={() => {}}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path={path} element={page} />
        </Routes>
      </MemoryRouter>
    </SessionProvider>,
  )
}
