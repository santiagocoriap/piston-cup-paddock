import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { ProtestExtras } from './ProtestExtras'

afterEach(() => vi.restoreAllMocks())

const protest = (extra = {}) => ({
  id: 4, attempt: 1, submitted_by: 'racer', involved: ['Ana'], lap: 3, description: 'Me tocó', status: 'dismissed',
  decision: 'Incidente', decided_by: 'santi', created_at: '2026-10-12T10:00:00Z',
  evidence: [
    { id: 1, url: 'https://youtu.be/abc', filename: '', content_type: '', uploaded_by: 'racer' },
    { id: 2, url: '', filename: 't1.mp4', content_type: 'video/mp4', uploaded_by: 'racer' },
  ],
  appeal_status: '', appeal_reason: '', appeal_decision: '', appeal_decided_by: null, can_appeal: true,
  ...extra,
})

const page = { path: '/rounds/:roundId', url: '/rounds/9', me: DRIVER }

describe('ProtestExtras', () => {
  it('shows the evidence and lets the author appeal once', async () => {
    const calls = mockApi({ 'POST /api/protests/4/appeal': () => json(200, {}) })
    const onChange = vi.fn()
    renderPage(<ProtestExtras protest={protest()} canDecide={false} onChange={onChange} />, page)
    expect(screen.getByRole('link', { name: 'https://youtu.be/abc' })).toHaveAttribute('href', 'https://youtu.be/abc')
    expect(screen.getByRole('link', { name: 't1.mp4' })).toHaveAttribute('href', '/api/protest-evidence/2')
    await userEvent.type(screen.getByLabelText('¿Por qué apelás? (una sola vez)'), 'Video nuevo')
    await userEvent.click(screen.getByRole('button', { name: 'Apelar' }))
    await vi.waitFor(() => expect(onChange).toHaveBeenCalled())
    expect(calls.find((c) => c.key === 'POST /api/protests/4/appeal')!.body).toEqual({ reason: 'Video nuevo' })
  })

  it('lets a steward decide an open appeal', async () => {
    mockApi({ 'POST /api/protests/4/appeal-decision': () => json(200, {}) })
    renderPage(
      <ProtestExtras protest={protest({ appeal_status: 'open', appeal_reason: 'Video', can_appeal: false })} canDecide onChange={vi.fn()} />,
      page,
    )
    expect(screen.getByText('Apelación pendiente: Video')).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Decidir la apelación' })).toBeInTheDocument()
  })
})
