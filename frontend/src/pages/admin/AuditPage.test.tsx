import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    const change = (await screen.findByText('DNF · P4 · 12 pts')).closest('li')!
    expect(change).toHaveTextContent('BingP2 · 18 ptsDNF · P4 · 12 pts')
    expect(within(change).getByText('P2 · 18 pts')).toHaveClass('audit-old')
    expect(screen.getByText('Abandonó en la vuelta 9').closest('blockquote')).toHaveTextContent('MotivoAbandonó en la vuelta 9')
  })

  it('uses the language of the user', async () => {
    await i18n.changeLanguage('en')
    show()
    expect(
      await screen.findByRole('link', { name: 'santi changed the result of round 1 (Highlands - Long).' }),
    ).toBeInTheDocument()
  })

  it('joins repeated changes and puts them under the day', async () => {
    const now = new Date()
    const report = (id: number, number: number, minutesAgo: number) => ({
      ...entry, id, action: 'report.requested', changes: [], reason: '',
      created_at: new Date(now.getTime() - minutesAgo * 60_000).toISOString(), params: { ...entry.params, report: number },
    })
    mockApi({
      'GET /api/championships': () => json(200, []),
      'GET /api/audit': () => json(200, [report(3, 3, 1), report(2, 2, 2), report(1, 1, 3)]),
    })
    renderPage(<AuditPage />, { path: '/admin/audit', url: '/admin/audit' })
    const today = await screen.findByRole('region', { name: 'Hoy' })
    expect(within(today).getAllByRole('link')).toHaveLength(1)
    expect(within(today).getByText('2 más como este')).toBeInTheDocument()
    expect(screen.getByText('3 cambios')).toBeInTheDocument()
  })

  it('filters by kind and by text', async () => {
    const created = { ...entry, id: 2, action: 'driver.created', target_type: 'driver', target_id: 4, params: { driver: 'Bing' }, changes: [], reason: '' }
    mockApi({
      'GET /api/championships': () => json(200, []),
      'GET /api/audit': () => json(200, [created, entry]),
    })
    renderPage(<AuditPage />, { path: '/admin/audit', url: '/admin/audit' })
    expect(await screen.findByText('2 cambios')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Resultados' }))
    expect(screen.getByRole('button', { name: 'Resultados' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('1 cambio')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Todo' }))
    await userEvent.type(screen.getByPlaceholderText('Persona, cambio o motivo'), 'vuelta 9')
    expect(screen.getByText('1 cambio')).toBeInTheDocument()
    await userEvent.clear(screen.getByPlaceholderText('Persona, cambio o motivo'))
    await userEvent.type(screen.getByPlaceholderText('Persona, cambio o motivo'), 'nada')
    expect(screen.getByText('Ningún cambio coincide con estos filtros.')).toBeInTheDocument()
  })
})
