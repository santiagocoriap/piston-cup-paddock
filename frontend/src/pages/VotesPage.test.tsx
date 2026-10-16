import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { VotesPage } from './VotesPage'

afterEach(() => vi.restoreAllMocks())

const ballot = (id: number, status: string, voted: boolean) => ({
  id, kind: 'track', title: `Pistas ${id}`, status, parent_id: null, winners: status === 'decided' ? ['Spa'] : [],
  closes_at: null, voted, championship: 'Piston Cup', season: '2027',
})

describe('VotesPage', () => {
  it('shows the open votes first, with a button for the vote that waits', async () => {
    mockApi({
      'GET /api/me/ballots': () => json(200, [ballot(1, 'open', false), ballot(2, 'open', true), ballot(3, 'decided', true)]),
    })
    renderPage(<VotesPage />, { path: '/votes', url: '/votes', me: DRIVER })
    expect(await screen.findByRole('link', { name: 'Votar' })).toHaveAttribute('href', '/ballots/1')
    expect(screen.getByText('Ya votaste')).toBeInTheDocument()
    expect(screen.getByText(/Elegidas: Spa/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Abiertas' })).toBeInTheDocument()
  })

  it('says when there is no vote', async () => {
    mockApi({ 'GET /api/me/ballots': () => json(200, []) })
    renderPage(<VotesPage />, { path: '/votes', url: '/votes', me: DRIVER })
    expect(await screen.findByText('No hay votaciones')).toBeInTheDocument()
  })
})
