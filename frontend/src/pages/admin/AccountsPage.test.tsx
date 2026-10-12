import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../../test-utils'
import { AccountsPage } from './AccountsPage'

afterEach(() => vi.restoreAllMocks())

const account = {
  id: 5, username: 'bing', driver_name: 'Bing', championships: ['LMDh (driver)'], has_password: false,
  open_link: true, last_login: null,
}

describe('AccountsPage', () => {
  it('makes an account and shows the full invite link', async () => {
    const calls = mockApi({
      'GET /api/accounts': () => json(200, []),
      'GET /api/drivers': () => json(200, [{ id: 3, display_name: 'Bing', steam_guid: null, user_id: null, username: null, career_points: 0 }]),
      'GET /api/championships': () => json(200, [{ id: 1, name: 'LMDh', league_id: 1, league_name: 'L', can_manage: true }]),
      'POST /api/accounts': () =>
        json(201, { account, link_path: '/invite#tok123', expires_at: '2026-10-19T00:00:00Z' }),
    })
    renderPage(<AccountsPage />, { path: '/admin/accounts', url: '/admin/accounts' })
    const form = await screen.findByRole('form', { name: 'Nueva cuenta' })
    await userEvent.type(within(form).getByLabelText('Usuario'), 'bing')
    await within(form).findByRole('option', { name: 'Bing' })
    await userEvent.selectOptions(within(form).getByLabelText('Piloto (opcional)'), '3')
    await userEvent.selectOptions(within(form).getByLabelText('Campeonato (opcional)'), '1')
    await userEvent.click(within(form).getByRole('button', { name: 'Crear cuenta' }))

    const box = await screen.findByRole('region', { name: 'Link para bing' })
    expect(within(box).getByRole('textbox')).toHaveValue(`${window.location.origin}/invite#tok123`)
    expect(calls.find((c) => c.key === 'POST /api/accounts')!.body).toEqual({
      username: 'bing', driver_id: 3, championship_id: 1, role: 'driver',
    })
  })
})
