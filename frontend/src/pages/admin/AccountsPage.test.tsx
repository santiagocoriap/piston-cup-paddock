import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../../test-utils'
import { AccountsPage } from './AccountsPage'

afterEach(() => vi.restoreAllMocks())

const account = {
  id: 5, username: 'bing', is_platform_admin: false, driver_name: 'Bing', championships: ['LMDh (driver)'], has_password: false,
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
    await userEvent.click(await screen.findByRole('button', { name: 'Nueva cuenta' }))
    const form = await screen.findByRole('form', { name: 'Nueva cuenta' })
    expect(within(form).getByLabelText('Rol')).toBeDisabled()
    await userEvent.type(within(form).getByLabelText('Usuario'), 'bing')
    await within(form).findByRole('option', { name: 'Bing' })
    await userEvent.selectOptions(within(form).getByLabelText('Piloto (opcional)'), '3')
    await userEvent.selectOptions(within(form).getByLabelText('Campeonato (opcional)'), '1')
    expect(within(form).getByLabelText('Rol')).toBeEnabled()
    await userEvent.click(within(form).getByRole('button', { name: 'Crear cuenta' }))

    const box = await screen.findByRole('region', { name: 'Link para bing' })
    expect(screen.getByRole('dialog', { name: 'Link listo' })).toHaveAttribute('open')
    expect(within(box).getByRole('textbox')).toHaveValue(`${window.location.origin}/invite#tok123`)
    expect(calls.find((c) => c.key === 'POST /api/accounts')!.body).toEqual({
      username: 'bing', driver_id: 3, new_driver: false, steam_guid: null, championship_id: 1, role: 'driver', platform_admin: false,
    })
  })

  it('makes a password link for an active account from the row menu', async () => {
    const active = { ...account, id: 1, username: 'santi', has_password: true, open_link: false, last_login: '2026-10-13T03:41:00Z' }
    const calls = mockApi({
      'GET /api/accounts': () => json(200, [active, account]),
      'GET /api/drivers': () => json(200, []),
      'GET /api/championships': () => json(200, []),
      'POST /api/accounts/1/link': () => json(200, { account: active, link_path: '/invite#reset1', expires_at: '2026-10-19T00:00:00Z' }),
    })
    renderPage(<AccountsPage />, { path: '/admin/accounts', url: '/admin/accounts' })
    expect((await screen.findByText('bing')).closest('tr')).toHaveTextContent('Esperando contraseña')
    await userEvent.click(screen.getByRole('button', { name: 'Acciones de santi' }))
    await userEvent.click(screen.getByRole('button', { name: 'Nuevo link para cambiar la contraseña' }))
    const box = await screen.findByRole('region', { name: 'Link para santi' })
    expect(within(box).getByRole('textbox')).toHaveValue(`${window.location.origin}/invite#reset1`)
    expect(calls.some((c) => c.key === 'POST /api/accounts/1/link')).toBe(true)
    await userEvent.click(within(box).getByRole('button', { name: 'Listo' }))
    expect(screen.queryByRole('region', { name: 'Link para santi' })).not.toBeInTheDocument()
  })

  it('filters by username, driver, or championship', async () => {
    mockApi({
      'GET /api/accounts': () => json(200, [{ ...account, id: 1, username: 'santi', driver_name: null, championships: [] }, account]),
      'GET /api/drivers': () => json(200, []),
      'GET /api/championships': () => json(200, []),
    })
    renderPage(<AccountsPage />, { path: '/admin/accounts', url: '/admin/accounts' })
    await userEvent.type(await screen.findByPlaceholderText('Usuario, piloto o campeonato'), 'lmdh')
    expect(screen.getByText('1 cuenta')).toBeInTheDocument()
    expect(screen.queryByText('santi')).not.toBeInTheDocument()
  })

  it('makes an account a platform admin after a confirmation', async () => {
    const calls = mockApi({
      'GET /api/accounts': () => json(200, [account]),
      'GET /api/drivers': () => json(200, []),
      'GET /api/championships': () => json(200, []),
      'PUT /api/accounts/5/platform-admin': () => json(200, { ...account, is_platform_admin: true }),
    })
    renderPage(<AccountsPage />, { path: '/admin/accounts', url: '/admin/accounts' })
    await userEvent.click(await screen.findByRole('button', { name: /bing/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Hacer admin de la plataforma' }))
    const dialog = await screen.findByRole('dialog', { name: 'Hacer admin de la plataforma' })
    expect(within(dialog).getByText(/bing va a tener el mismo acceso que vos/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Hacer admin de la plataforma' }))
    await vi.waitFor(() =>
      expect(calls.find((c) => c.key === 'PUT /api/accounts/5/platform-admin')!.body).toEqual({ on: true }),
    )
  })
})
