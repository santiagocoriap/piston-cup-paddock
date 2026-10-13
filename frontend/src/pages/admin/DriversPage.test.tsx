import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../../test-utils'
import { DriversPage } from './DriversPage'

afterEach(() => vi.restoreAllMocks())

const driver = (id: number, name: string, guid: string | null, userId: number | null = null, username: string | null = null) => ({
  id, display_name: name, steam_guid: guid, user_id: userId, username, career_points: id * 10,
})

const drivers = [
  driver(1, 'Ana López', '76561190000000001', 7, 'ana'),
  driver(2, 'Juan', '76561190000000002'),
  driver(3, 'Juan Pérez', null),
]
const users = [{ id: 7, username: 'ana' }, { id: 8, username: 'juan' }]

const profile = (seasonIds: number[], records = 0) => ({
  id: 0, display_name: '', can_adjust: true,
  career: { raw_points: 0, points: 0, level: 1, next_level_points: 0, adjustments: [] },
  seasons: seasonIds.map((id) => ({
    season_id: id, season_name: String(2020 + id), championship_name: 'LMDh',
    rank: 1, entries: 1, points: 0, wins: 0, podiums: 0, starts: 0,
  })),
  safety: [],
  records: Array.from({ length: records }, (_, i) => ({ track: 'T', car: 'C', category: 'race', lap_time_ms: 1, round_id: i })),
  restarts_caused: [],
})

function routes(extra = {}) {
  return {
    'GET /api/drivers': () => json(200, drivers),
    'GET /api/users': () => json(200, users),
    'GET /api/drivers/1/profile': () => json(200, profile([6], 2)),
    'GET /api/drivers/2/profile': () => json(200, profile([5])),
    'GET /api/drivers/3/profile': () => json(200, profile([6])),
    ...extra,
  }
}

async function openMenu(name: string) {
  await userEvent.click(await screen.findByRole('button', { name: `Acciones de ${name}` }))
}

describe('DriversPage', () => {
  it('shows each driver with a profile link and an account badge', async () => {
    mockApi(routes())
    renderPage(<DriversPage />, { path: '/admin/drivers', url: '/admin/drivers' })
    const row = (await screen.findByRole('link', { name: 'Ana López' })).closest('tr')!
    expect(within(row).getByRole('link', { name: 'Ana López' })).toHaveAttribute('href', '/drivers/1')
    expect(row).toHaveTextContent('AL')
    expect(row).toHaveTextContent('@ana')
    expect(screen.getByRole('link', { name: 'Juan' }).closest('tr')).toHaveTextContent('Sin cuenta')
  })

  it('filters by name, Steam GUID, or account', async () => {
    mockApi(routes())
    renderPage(<DriversPage />, { path: '/admin/drivers', url: '/admin/drivers' })
    const search = await screen.findByPlaceholderText('Nombre, Steam GUID o cuenta')
    await userEvent.type(search, '0002')
    expect(screen.getAllByRole('row')).toHaveLength(2)
    expect(screen.getByText('1 piloto')).toBeInTheDocument()
    await userEvent.clear(search)
    await userEvent.type(search, 'nadie')
    expect(screen.getByText('Ningún piloto coincide con «nadie».')).toBeInTheDocument()
  })

  it('shows an empty state with a create button', async () => {
    mockApi(routes({ 'GET /api/drivers': () => json(200, []) }))
    renderPage(<DriversPage />, { path: '/admin/drivers', url: '/admin/drivers' })
    expect(await screen.findByText('Todavía no hay pilotos.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Nuevo piloto' }))
    expect(screen.getByRole('dialog', { name: 'Nuevo piloto' })).toHaveAttribute('open')
  })
})

describe('DriversPage account link', () => {
  it('links an account from a searchable list and says it is saved', async () => {
    const calls = mockApi(routes({ 'POST /api/drivers/2/link': () => json(200, driver(2, 'Juan', null, 8, 'juan')) }))
    renderPage(<DriversPage />, { path: '/admin/drivers', url: '/admin/drivers' })
    await openMenu('Juan')
    await userEvent.click(screen.getByRole('button', { name: 'Vincular cuenta' }))
    const dialog = screen.getByRole('dialog', { name: 'Vincular cuenta: Juan' })
    const save = within(dialog).getByRole('button', { name: 'Guardar' })
    expect(save).toBeDisabled()
    await userEvent.click(within(dialog).getByRole('combobox', { name: 'Cuenta' }))
    expect(within(dialog).getByRole('option', { name: /ana/ })).toHaveAttribute('aria-disabled', 'true')
    expect(within(dialog).getByRole('option', { name: /ana/ })).toHaveTextContent('Vinculada a Ana López')
    await userEvent.type(within(dialog).getByRole('combobox', { name: 'Cuenta' }), 'jua{Enter}')
    await userEvent.click(save)
    expect(await within(dialog).findByRole('status')).toHaveTextContent('Cuenta guardada.')
    expect(calls.find((c) => c.key === 'POST /api/drivers/2/link')!.body).toEqual({ user_id: 8 })
  })
})

describe('DriversPage merge', () => {
  it('compares the two profiles and merges after the reason and the check', async () => {
    const calls = mockApi(routes({ 'POST /api/drivers/3/merge': () => json(200, drivers[1]) }))
    renderPage(<DriversPage />, { path: '/admin/drivers', url: '/admin/drivers' })
    await openMenu('Juan Pérez')
    await userEvent.click(screen.getByRole('button', { name: 'Unir con…' }))
    const dialog = screen.getByRole('dialog', { name: 'Unir dos perfiles' })
    const merge = within(dialog).getByRole('button', { name: 'Unir' })
    expect(merge).toBeDisabled()
    expect(within(dialog).queryByRole('option', { name: /Juan Pérez/ })).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('combobox', { name: 'Perfil que queda' }))
    expect(within(dialog).queryByRole('option', { name: /Juan Pérez/ })).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('option', { name: 'Juan' }))
    expect(await within(dialog).findByRole('region', { name: 'Queda: Juan' })).toHaveTextContent('LMDh 2025')
    expect(within(dialog).getByRole('region', { name: 'Se borra: Juan Pérez' })).toHaveTextContent('LMDh 2026')
    await userEvent.type(within(dialog).getByLabelText('Motivo'), 'Mismo piloto')
    expect(merge).toBeDisabled()
    await userEvent.click(within(dialog).getByRole('checkbox'))
    await userEvent.click(merge)
    expect(await screen.findByRole('status')).toHaveTextContent('«Juan Pérez» se unió a «Juan».')
    expect(calls.find((c) => c.key === 'POST /api/drivers/3/merge')!.body).toEqual({ into_id: 2, reason: 'Mismo piloto' })
  })

  it('blocks a merge of two profiles in the same season', async () => {
    mockApi(routes())
    renderPage(<DriversPage />, { path: '/admin/drivers', url: '/admin/drivers' })
    await openMenu('Juan Pérez')
    await userEvent.click(screen.getByRole('button', { name: 'Unir con…' }))
    const dialog = screen.getByRole('dialog', { name: 'Unir dos perfiles' })
    await userEvent.click(within(dialog).getByRole('combobox', { name: 'Perfil que queda' }))
    await userEvent.click(within(dialog).getByRole('option', { name: /Ana López/ }))
    expect(await within(dialog).findByText('Los dos perfiles corren la misma temporada.')).toBeInTheDocument()
    await userEvent.type(within(dialog).getByLabelText('Motivo'), 'x')
    await userEvent.click(within(dialog).getByRole('checkbox'))
    expect(within(dialog).getByRole('button', { name: 'Unir' })).toBeDisabled()
  })

  it('swaps the profile that stays', async () => {
    mockApi(routes())
    renderPage(<DriversPage />, { path: '/admin/drivers', url: '/admin/drivers' })
    await openMenu('Juan Pérez')
    await userEvent.click(screen.getByRole('button', { name: 'Unir con…' }))
    const dialog = screen.getByRole('dialog', { name: 'Unir dos perfiles' })
    await userEvent.click(within(dialog).getByRole('combobox', { name: 'Perfil que queda' }))
    await userEvent.click(within(dialog).getByRole('option', { name: 'Juan' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Invertir' }))
    expect(within(dialog).getByRole('region', { name: 'Se borra: Juan' })).toBeInTheDocument()
    expect(within(dialog).getByRole('region', { name: 'Queda: Juan Pérez' })).toBeInTheDocument()
  })
})
