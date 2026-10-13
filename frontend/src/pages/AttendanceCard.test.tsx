import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NotificationBell } from '../components/NotificationBell'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { AttendanceCard } from './AttendanceCard'

afterEach(() => vi.restoreAllMocks())

const attendance = (mine: string | null, yes: number) => ({
  mine, can_answer: true, yes, maybe: 0, no: 1,
  rows: [{ entry_id: 1, driver_name: 'Ana', answer: mine }, { entry_id: 2, driver_name: 'Beto', answer: 'no' }],
})

describe('AttendanceCard', () => {
  it('sends the answer and shows the new counts', async () => {
    const calls = mockApi({
      'GET /api/rounds/9/attendance': () => json(200, attendance(null, 0)),
      'PUT /api/rounds/9/attendance': () => json(200, attendance('yes', 1)),
    })
    renderPage(<AttendanceCard roundId={9} />, { path: '/rounds/:roundId', url: '/rounds/9', me: DRIVER })
    expect(await screen.findByText('0 sí · 0 tal vez · 1 no')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Sí' }))
    expect(await screen.findByText('1 sí · 0 tal vez · 1 no')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sí' })).toHaveAttribute('aria-pressed', 'true')
    expect(calls.find((c) => c.key === 'PUT /api/rounds/9/attendance')!.body).toEqual({ answer: 'yes' })
  })
})

describe('NotificationBell', () => {
  it('shows the unread count and marks all as read', async () => {
    const item = { id: 3, kind: 'result.official', params: { championship: 'LMDh', number: 1, track: 'Spa' }, link: '/rounds/9', created_at: '2026-10-12T10:00:00Z', read: false }
    const calls = mockApi({
      'GET /api/me/notifications': () => json(200, { unread: 1, items: [item] }),
      'POST /api/me/notifications/read': () => json(200, { unread: 0, items: [{ ...item, read: true }] }),
    })
    render(
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>,
    )
    const bell = await screen.findByRole('button', { name: 'Notificaciones (1 sin leer)' })
    await userEvent.click(bell)
    expect(screen.getByText('Resultado oficial: LMDh R1 · Spa')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Marcar todo como leído' }))
    expect(await screen.findByRole('button', { name: 'Notificaciones (0 sin leer)' })).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/me/notifications/read')!.body).toEqual({ ids: [] })
  })
})
