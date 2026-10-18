import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { CollectorsSection } from './CollectorsSection'

afterEach(() => vi.restoreAllMocks())

const collector = { id: 1, name: 'Servidor AC', created_at: '2026-10-12T10:00:00Z', last_seen_at: null, revoked: false, files: 1, events: 0 }
const file = {
  id: 7, collector: 'Servidor AC', kind: 'result', filename: '2026_10_11_20_7_RACE.json', session_type: 'race',
  track: 'ks_highlands', session_time: '2026-10-11T23:07:00Z', round_id: null, status: 'unmatched', error: '',
  received_at: '2026-10-12T10:00:00Z',
}
const rounds = [{ id: 3, season_name: '2026', number: 1, track_name: 'Highlands', scheduled_at: null }]

describe('CollectorsSection', () => {
  it('makes a key once and assigns a file without a round', async () => {
    const calls = mockApi({
      'GET /api/championships/2/collectors': () => json(200, { collectors: [collector], rounds, files: [file] }),
      'POST /api/championships/2/collectors': () => json(201, { ...collector, id: 2, name: 'Otro', key: 'pcc_secret' }),
      'POST /api/collector-files/7/assign': () =>
        json(200, { collectors: [collector], rounds, files: [{ ...file, status: 'assigned', round_id: 3 }] }),
    })
    renderPage(<CollectorsSection championshipId={2} />, { path: '/championships/:id', url: '/championships/2' })
    expect(await screen.findByText('nunca se conectó', { exact: false })).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Nombre'), 'Otro')
    await userEvent.click(screen.getByRole('button', { name: 'Crear clave' }))
    expect(await screen.findByDisplayValue('pcc_secret')).toBeInTheDocument()
    expect(screen.getByText(/La app no la muestra otra vez/)).toBeInTheDocument()
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    await userEvent.click(screen.getByRole('button', { name: 'Copiar clave' }))
    expect(writeText).toHaveBeenCalledWith('pcc_secret')
    expect(await screen.findByRole('button', { name: 'Copiada' })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Fecha para 2026_10_11_20_7_RACE.json'), '3')
    await userEvent.click(screen.getByRole('button', { name: 'Asignar' }))
    expect(await screen.findByText(/en la fecha/)).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/collector-files/7/assign')!.body).toEqual({ round_id: 3 })
  })

  it('downloads the collector zip with the new key', async () => {
    const objectUrl = vi.fn(() => 'blob:zip')
    Object.assign(URL, { createObjectURL: objectUrl, revokeObjectURL: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const calls = mockApi({
      'GET /api/championships/2/collectors': () => json(200, { collectors: [collector], rounds, files: [] }),
      'POST /api/championships/2/collectors': () => json(201, { ...collector, id: 2, name: 'Otro', key: 'pcc_secret' }),
      'POST /api/collectors/2/package': () => new Response('zip', { status: 200, headers: { 'Content-Type': 'application/zip' } }),
    })
    renderPage(<CollectorsSection championshipId={2} />, { path: '/championships/:id', url: '/championships/2' })
    await userEvent.type(await screen.findByLabelText('Nombre'), 'Otro')
    await userEvent.click(screen.getByRole('button', { name: 'Crear clave' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Descargar colector' }))
    await vi.waitFor(() => expect(click).toHaveBeenCalled())
    expect(calls.find((c) => c.key === 'POST /api/collectors/2/package')!.body).toEqual({ key: 'pcc_secret' })
  })

  it('says when there is no program yet', async () => {
    mockApi({
      'GET /api/championships/2/collectors': () => json(200, { collectors: [collector], rounds, files: [] }),
      'POST /api/championships/2/collectors': () => json(201, { ...collector, id: 2, name: 'Otro', key: 'pcc_secret' }),
      'POST /api/collectors/2/package': () => json(503, { detail: 'no_release' }),
    })
    renderPage(<CollectorsSection championshipId={2} />, { path: '/championships/:id', url: '/championships/2' })
    await userEvent.type(await screen.findByLabelText('Nombre'), 'Otro')
    await userEvent.click(screen.getByRole('button', { name: 'Crear clave' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Descargar colector' }))
    expect(await screen.findByText(/todavía no tiene el programa/)).toBeInTheDocument()
  })
})
