import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../../test-utils'
import { LeaguesPage } from './LeaguesPage'

afterEach(() => vi.restoreAllMocks())

const piston = {
  id: 1,
  name: 'Piston Cup',
  timezone: 'America/Argentina/Buenos_Aires',
  championships: [
    { id: 3, name: 'GT3', season_count: 1 },
    { id: 2, name: 'LMDh', season_count: 2 },
  ],
}

describe('LeaguesPage', () => {
  it('shows each league with its championships, counts, and timezone', async () => {
    mockApi({ 'GET /api/leagues': () => json(200, [piston]) })
    renderPage(<LeaguesPage />, { path: '/admin/leagues', url: '/admin/leagues' })
    const card = await screen.findByRole('article', { name: 'Piston Cup' })
    expect(within(card).getByRole('button', { name: /^Piston Cup/ })).toHaveTextContent('2 campeonatos · 3 temporadas')
    expect(within(card).getByText('Zona horaria: America/Argentina/Buenos_Aires')).toBeInTheDocument()
    const rows = within(card).getAllByRole('listitem')
    expect(rows.map((row) => row.textContent)).toEqual(['GT31 temporadaAbrir', 'LMDh2 temporadasAbrir'])
    expect(within(rows[1]).getByRole('link', { name: 'Abrir' })).toHaveAttribute('href', '/championships/2')
  })

  it('opens and closes a league', async () => {
    mockApi({ 'GET /api/leagues': () => json(200, [piston]) })
    renderPage(<LeaguesPage />, { path: '/admin/leagues', url: '/admin/leagues' })
    const toggle = await screen.findByRole('button', { name: /^Piston Cup/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('link', { name: 'Abrir' })).not.toBeInTheDocument()
  })

  it('adds a championship inside its league and shows it', async () => {
    let leagues = [{ ...piston, championships: [] as typeof piston.championships }]
    const calls = mockApi({
      'GET /api/leagues': () => json(200, leagues),
      'POST /api/leagues/1/championships': () => {
        leagues = [{ ...piston, championships: [{ id: 9, name: 'F1', season_count: 0 }] }]
        return json(201, { id: 9, name: 'F1' })
      },
    })
    renderPage(<LeaguesPage />, { path: '/admin/leagues', url: '/admin/leagues' })
    expect(await screen.findByText('Esta liga todavía no tiene campeonatos.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Nuevo campeonato' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Nombre del campeonato' }), 'F1')
    await userEvent.click(screen.getByRole('button', { name: 'Crear' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Campeonato «F1» creado.')
    expect(await screen.findByText('F1')).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/leagues/1/championships')!.body).toEqual({ name: 'F1' })
  })

  it('shows the API error on the add row', async () => {
    mockApi({
      'GET /api/leagues': () => json(200, [piston]),
      'POST /api/leagues/1/championships': () => json(409, { detail: 'championship_exists' }),
    })
    renderPage(<LeaguesPage />, { path: '/admin/leagues', url: '/admin/leagues' })
    await userEvent.click(await screen.findByRole('button', { name: 'Nuevo campeonato' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Nombre del campeonato' }), 'LMDh')
    await userEvent.click(screen.getByRole('button', { name: 'Crear' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('creates a league from the header dialog', async () => {
    const calls = mockApi({
      'GET /api/leagues': () => json(200, [piston]),
      'POST /api/leagues': () => json(201, { id: 5, name: 'Otra', timezone: 'UTC', championships: [] }),
    })
    renderPage(<LeaguesPage />, { path: '/admin/leagues', url: '/admin/leagues' })
    await userEvent.click(await screen.findByRole('button', { name: 'Nueva liga' }))
    const dialog = screen.getByRole('dialog', { name: 'Nueva liga' })
    await userEvent.type(within(dialog).getByLabelText('Nombre'), 'Otra')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Crear' }))
    await vi.waitFor(() => expect(dialog).not.toHaveAttribute('open'))
    expect(calls.find((c) => c.key === 'POST /api/leagues')!.body).toEqual({ name: 'Otra' })
  })

  it('shows an empty state with a create button when there are no leagues', async () => {
    mockApi({ 'GET /api/leagues': () => json(200, []) })
    renderPage(<LeaguesPage />, { path: '/admin/leagues', url: '/admin/leagues' })
    expect(await screen.findByText('Todavía no hay ligas.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Nueva liga' }))
    expect(screen.getByRole('dialog', { name: 'Nueva liga' })).toHaveAttribute('open')
  })
})
