import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { oauthReturn } from '../App'
import { ADMIN, json, mockApi, renderPage } from '../test-utils'
import { ConnectionsCard } from './ConnectionsCard'

afterEach(() => {
  vi.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

describe('ConnectionsCard', () => {
  it('shows the MCP address and removes a connection', async () => {
    const calls = mockApi({
      'GET /api/me/connections': () =>
        json(200, [
          { application_id: 3, name: 'Claude', connected_at: '2026-10-22T10:00:00Z', last_access_at: '2026-10-22T11:00:00Z', active: true },
        ]),
      'DELETE /api/me/connections/3': () => new Response(null, { status: 204 }),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage(<ConnectionsCard />, { path: '/', url: '/', me: ADMIN })
    expect(screen.getByDisplayValue(`${window.location.origin}/mcp`)).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Quitar acceso' }))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'DELETE /api/me/connections/3')).toBe(true))
  })
})

describe('oauthReturn', () => {
  it('goes back only to an OAuth page of this server', () => {
    window.history.replaceState(null, '', '/sign-in?next=%2Foauth%2Fauthorize%2F%3Fclient_id%3Dx')
    expect(oauthReturn()).toBe('/oauth/authorize/?client_id=x')
    window.history.replaceState(null, '', '/sign-in?next=https%3A%2F%2Fevil.example.com')
    expect(oauthReturn()).toBeNull()
    window.history.replaceState(null, '', '/seasons/1?next=%2Foauth%2Fauthorize%2F')
    expect(oauthReturn()).toBeNull()
  })
})
