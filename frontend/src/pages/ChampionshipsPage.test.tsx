import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, DRIVER, json, mockApi, renderPage } from '../test-utils'
import { ChampionshipsPage } from './ChampionshipsPage'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

const championship = { id: 1, name: 'Demo LMDh', league_id: 1, league_name: 'Piston Cup', can_manage: true, provisional_reports: false }
const season = { id: 4, name: '2026', planned_round_count: 8, protest_window_minutes: 60, allow_repeat_layouts: false, voted_slots: 0 }
const detail = {
  ...championship,
  seasons: [season],
  latest: {
    season_id: 4, name: '2026', done: 1, total: 8, leader: 'Driver 03',
    next_round: { round_id: 9, number: 2, track_name: 'Highlands', layout_name: 'Long', scheduled_at: null },
  },
}
const pending = [
  {
    kind: 'results', count: 6,
    items: [1, 2, 3, 4, 5].map((n) => ({ path: `/rounds/${n}`, championship: 'Demo LMDh', name: 'Highlands · Long', number: n })),
  },
  { kind: 'images', count: 3, items: [] },
]

function mockHome(extra: Record<string, () => Response> = {}) {
  return mockApi({
    'GET /api/dashboard': () => json(200, { has_driver_profile: false, seasons: [] }),
    'GET /api/championships': () => json(200, [championship]),
    'GET /api/championships/1': () => json(200, detail),
    'GET /api/pending': () => json(200, pending),
    ...extra,
  })
}

describe('Home for an admin', () => {
  it('lists what is pending, with links and the count of the rest', async () => {
    mockHome()
    renderPage(<ChampionshipsPage />, { path: '/', url: '/', me: ADMIN })
    const list = await screen.findByRole('heading', { name: 'Pendiente' })
    const section = list.closest('section')!
    expect(within(section).getByText('6 resultados para aprobar')).toBeInTheDocument()
    expect(within(section).getByRole('link', { name: 'Fecha 1 · Highlands · Long' })).toHaveAttribute('href', '/rounds/1')
    expect(within(section).getByText('y 1 más')).toBeInTheDocument()
    expect(within(section).getByText('3 pistas o autos sin imagen')).toBeInTheDocument()
    expect(within(section).getByRole('link', { name: 'Abrir' })).toHaveAttribute('href', '/admin/catalog?tab=images')
  })

  it('says when nothing is pending', async () => {
    mockHome({ 'GET /api/pending': () => json(200, []) })
    renderPage(<ChampionshipsPage />, { path: '/', url: '/', me: ADMIN })
    expect(await screen.findByText('Nada pendiente.')).toBeInTheDocument()
  })

  it('shows the progress, the next round, and the leader on the card', async () => {
    mockHome()
    renderPage(<ChampionshipsPage />, { path: '/', url: '/', me: ADMIN })
    const card = (await screen.findByText('Líder: Driver 03')).closest('li')!
    expect(card).toHaveTextContent('2026 · 1 de 8 fechas')
    expect(card).toHaveTextContent('Próxima: Fecha 2 · Highlands · Long · Sin fecha')
    // One way into the championship: the season is plain text.
    expect(within(card).queryByRole('link', { name: '2026' })).not.toBeInTheDocument()
  })

  it('links the admin account to a free driver profile', async () => {
    const calls = mockHome({
      'GET /api/drivers': () =>
        json(200, [
          { id: 3, display_name: 'Driver 03', steam_guid: null, user_id: null, username: null, career_points: 0 },
          { id: 4, display_name: 'Taken', steam_guid: null, user_id: 9, username: 'other', career_points: 0 },
        ]),
      'POST /api/drivers/3/link': () => json(200, {}),
    })
    renderPage(<ChampionshipsPage />, { path: '/', url: '/', me: ADMIN })
    expect(await screen.findByText('Elegí tu perfil de piloto para ver tus carreras acá.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Elegí tu perfil' }))
    const dialog = screen.getByRole('dialog', { name: 'Vincular mi cuenta' })
    await userEvent.click(await within(dialog).findByRole('combobox', { name: 'Perfil de piloto' }))
    expect(within(dialog).queryByRole('option', { name: /Taken/ })).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('option', { name: 'Driver 03' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Tu cuenta quedó vinculada a Driver 03.')).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/drivers/3/link')!.body).toEqual({ user_id: ADMIN.id })
  })

  it('hides the link box and remembers it', async () => {
    mockHome()
    const first = renderPage(<ChampionshipsPage />, { path: '/', url: '/', me: ADMIN })
    await userEvent.click(await screen.findByRole('button', { name: 'No corro en esta liga' }))
    expect(screen.queryByText('Todavía no corrés con esta cuenta')).not.toBeInTheDocument()
    first.unmount()
    renderPage(<ChampionshipsPage />, { path: '/', url: '/', me: ADMIN })
    await screen.findByText('Líder: Driver 03')
    expect(screen.queryByText('Todavía no corrés con esta cuenta')).not.toBeInTheDocument()
  })
})

describe('Home for a driver', () => {
  it('asks an admin to link the profile, and shows no pending list', async () => {
    mockHome()
    renderPage(<ChampionshipsPage />, { path: '/', url: '/', me: DRIVER })
    expect(await screen.findByText(/Pedile a un admin que lo vincule/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Elegí tu perfil' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Pendiente' })).not.toBeInTheDocument()
  })
})
