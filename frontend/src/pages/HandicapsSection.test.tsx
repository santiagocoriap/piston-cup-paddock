import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { HandicapsSection } from './HandicapsSection'

afterEach(() => vi.restoreAllMocks())

const step = (round: number, extra: Record<string, unknown>) => ({
  round_id: round, round_number: round, position: 1, status: 'finished', outcome: 'win', season_wins: 1,
  before_kg: 0, before_pct: 0, change_kg: 10, change_pct: 2, capped: false, after_kg: 10, after_pct: 2,
  used_kg: 0, used_pct: 0, adjustment_reason: null, ...extra,
})

const data = {
  next_round_id: 3, next_round_number: 3, can_manage: true,
  rules: { ballast_steps: [10, 10, 5, 3], restrictor_steps: [2, 2, 1], ballast_cap: 45, restrictor_cap: 5, ballast_reduction: 3, restrictor_reduction: 1 },
  entries: [
    {
      entry_id: 1, number: 1, driver_name: 'Ana', next_kg: 7, next_pct: 1, next_adjustment_reason: null,
      rounds: [
        step(1, {}),
        step(2, { position: 2, outcome: 'loss', before_kg: 10, before_pct: 2, change_kg: -3, change_pct: -1, after_kg: 7, after_pct: 1, used_kg: 20, used_pct: 4 }),
      ],
    },
  ],
}

const rounds = [
  { id: 1, number: 1, track_layout_id: 1, track_name: 'Highlands', layout_name: 'Long', scheduled_at: '2026-10-11T00:00:00Z', origin: 'manual', cancelled: false, cancel_reason: '', track_changes: [] },
  { id: 3, number: 3, track_layout_id: 1, track_name: 'Spa', layout_name: 'GP', scheduled_at: '2026-10-25T00:00:00Z', origin: 'manual', cancelled: false, cancel_reason: '', track_changes: [] },
]

function show(adminView: boolean, extra = {}) {
  const calls = mockApi({
    'GET /api/seasons/5/handicaps': () => json(200, data),
    ...extra,
  })
  renderPage(<HandicapsSection seasonId={5} rounds={rounds} adminView={adminView} />, {
    path: '/seasons/:seasonId',
    url: '/seasons/5',
    me: adminView ? undefined : DRIVER,
  })
  return calls
}

describe('HandicapsSection', () => {
  it('shows the values, the next round, and the explanation', async () => {
    show(false)
    const row = await screen.findByRole('row', { name: /Ana/ })
    expect(within(row).getByText('7 kg · 1 %')).toBeInTheDocument()
    expect(screen.getByText('Fecha 3 (próxima)')).toBeInTheDocument()
    const explain = screen.getByRole('list', { name: 'Explicación de Ana' })
    expect(explain).toHaveTextContent('Fecha 2: lleva 10 kg · 2 %, P2 → -3 kg -1 % = 7 kg · 1 %')
  })

  it('shows the used value when a correction changed the calculation', async () => {
    show(false)
    const cell = await screen.findByText('20 kg · 4 %')
    expect(cell).toHaveAttribute('title', expect.stringContaining('Corrió con 20 kg · 4 %'))
  })

  it('sends a manual adjustment with a reason', async () => {
    const calls = show(true, { 'POST /api/seasons/5/handicaps/adjustments': () => json(200, data) })
    await userEvent.click(await screen.findByRole('button', { name: 'Ajustar lastre y restrictor' }))
    const form = await screen.findByRole('form', { name: 'Ajustar lastre y restrictor' })
    await userEvent.selectOptions(within(form).getByLabelText('Piloto'), '1')
    await userEvent.type(within(form).getByLabelText('Lastre (kg)'), '5')
    await userEvent.type(within(form).getByLabelText('Restrictor (%)'), '0')
    await userEvent.type(within(form).getByLabelText('Motivo'), 'Problema con el auto')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar' }))
    const body = calls.find((c) => c.key === 'POST /api/seasons/5/handicaps/adjustments')!.body
    expect(body).toEqual({
      entry_id: 1, round_id: 3, ballast_kg: 5, restrictor_pct: 0, mode: 'temporary', reason: 'Problema con el auto',
    })
    // The dialog closes after the save.
    await vi.waitFor(() => expect(screen.queryByRole('form', { name: 'Ajustar lastre y restrictor' })).not.toBeInTheDocument())
  })
})
