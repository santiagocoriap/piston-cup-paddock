import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { json, mockApi, renderPage } from '../../test-utils'
import { AuditPage } from './AuditPage'

afterEach(async () => {
  vi.restoreAllMocks()
  await i18n.changeLanguage('es')
})

const entry = {
  id: 1,
  created_at: '2026-10-19T01:00:00Z',
  actor_name: 'santi',
  action: 'result.changed',
  championship_id: 1,
  championship_name: 'LMDh',
  target_type: 'round',
  target_id: 9,
  params: { season: '2026', number: 1, track: 'Highlands - Long' },
  changes: [
    {
      field: 'Bing',
      old: { status: 'finished', position: 2, points: 18 },
      new: { status: 'dnf', position: 4, points: 12 },
    },
  ],
  reason: 'Abandonó en la vuelta 9',
}

function show() {
  mockApi({
    'GET /api/championships': () => json(200, []),
    'GET /api/audit': () => json(200, [entry]),
  })
  renderPage(<AuditPage />, { path: '/admin/audit', url: '/admin/audit' })
}

describe('AuditPage', () => {
  it('shows a Spanish sentence that links to the round', async () => {
    show()
    const link = await screen.findByRole('link', {
      name: 'santi cambió el resultado de la fecha 1 (Highlands - Long).',
    })
    expect(link).toHaveAttribute('href', '/rounds/9')
  })

  it('shows the old and the new value, and the reason', async () => {
    show()
    const change = await screen.findByText(/DNF · P4 · 12 pts/)
    expect(change).toHaveTextContent('P2 · 18 pts → DNF · P4 · 12 pts')
    expect(screen.getByText('Motivo: Abandonó en la vuelta 9')).toBeInTheDocument()
  })

  it('uses the language of the user', async () => {
    await i18n.changeLanguage('en')
    show()
    expect(
      await screen.findByRole('link', { name: 'santi changed the result of round 1 (Highlands - Long).' }),
    ).toBeInTheDocument()
  })
})
