import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatLapTime } from '../lib/format'
import { json, mockApi, renderPage } from '../test-utils'
import { ImportSection } from './ImportSection'

afterEach(() => vi.restoreAllMocks())

const entries = [
  { entry_id: 1, driver_id: 11, number: 93, driver_name: 'Bing', car_name: 'Acura' },
  { entry_id: 2, driver_id: 12, number: 7, driver_name: 'Vice', car_name: 'Acura' },
]

function driver(position: number, entryId: number | null, name: string, extra = {}) {
  return {
    position, guid: `7656119000000000${position}`, name, car_model: 'acura', laps: 10,
    total_time_ms: 1964444, best_lap_ms: 189296, ballast_kg: 8, restrictor: 0,
    entry_id: entryId, driver_name: entryId ? name : null, warnings: [], ...extra,
  }
}

function imported(status = 'preview', unmatched = [driver(3, null, 'Guest')]) {
  return {
    id: 4, filename: 'RACE.json', sha256: 'abc', session_type: 'race', status,
    uploaded_by: 'santi', uploaded_at: '2026-10-12T01:00:00Z', applied_at: null, is_new: true,
    preview: {
      session_type: 'race', track: 'ks_highlands', layout: 'layout_long', attempt: 2,
      drivers: [driver(1, 1, 'Bing'), driver(2, 2, 'Vice', { laps: 9, warnings: ['fewer_laps'] })],
      unmatched, missing: ['conditions', 'penalties'], warnings: [],
    },
  }
}

function show(routes: Record<string, () => Response>) {
  const calls = mockApi({ 'GET /api/rounds/9/imports': () => json(200, []), ...routes })
  const onApplied = vi.fn()
  renderPage(<ImportSection roundId={9} entries={entries} onApplied={onApplied} />, {
    path: '/rounds/:roundId',
    url: '/rounds/9',
  })
  return { calls, onApplied }
}

async function uploadFile() {
  const file = new File(['{}'], 'RACE.json', { type: 'application/json' })
  const input = (await screen.findByLabelText('Archivo de resultados')) as HTMLInputElement
  await userEvent.upload(input, file)
  // jsdom marks a required file field as invalid, so the test sends the form directly.
  fireEvent.submit(input.form!)
}

describe('ImportSection', () => {
  it('formats lap and race times', () => {
    expect(formatLapTime(189296)).toBe('3:09.296')
    expect(formatLapTime(3_725_004)).toBe('1:02:05.004')
    expect(formatLapTime(null)).toBe('—')
  })

  it('shows the preview with matched and unmatched drivers', async () => {
    show({ 'POST /api/rounds/9/imports': () => json(201, imported()) })
    await uploadFile()
    const preview = await screen.findByRole('region', { name: 'Revisión del archivo' })
    expect(within(preview).getByText(/Se aplica a la largada 2/)).toBeInTheDocument()
    expect(within(preview).getByRole('row', { name: /Bing/ })).toHaveTextContent('3:09.296')
    expect(within(preview).getByText('Guest')).toBeInTheDocument()
    expect(within(preview).getByText(/Condiciones de pista y clima/)).toBeInTheDocument()
  })

  it('applies with a DNF and an ignored guest', async () => {
    const applied = imported('applied', [])
    const { calls, onApplied } = show({
      'POST /api/rounds/9/imports': () => json(201, imported()),
      'POST /api/imports/4/apply': () => json(200, applied),
    })
    await uploadFile()
    await userEvent.selectOptions(await screen.findByLabelText('Estado final Vice'), 'dnf')
    await userEvent.click(screen.getByLabelText('Ignorar'))
    await userEvent.click(screen.getByRole('button', { name: 'Aplicar el archivo' }))

    expect(await screen.findByText('Archivo aplicado.')).toBeInTheDocument()
    const body = calls.find((call) => call.key === 'POST /api/imports/4/apply')!.body
    expect(body).toEqual({ statuses: { 2: 'dnf' }, ignored_guids: ['76561190000000003'] })
    expect(onApplied).toHaveBeenCalled()
  })

  it('says when the same file comes again', async () => {
    show({ 'POST /api/rounds/9/imports': () => json(200, { ...imported('applied', []), is_new: false }) })
    await uploadFile()
    expect(await screen.findByText(/ya estaba subido/)).toBeInTheDocument()
  })
})

describe('ImportSection and the collector', () => {
  it('shows what the collector did with each file', async () => {
    const blocked = {
      ...imported(), id: 5, filename: 'RACE_2.json', uploaded_by: null, preview: null,
      auto_status: 'blocked', auto_reasons: ['handicap_differs', 'result_exists'], review_flags: [],
    }
    const published = {
      ...imported('applied'), id: 6, uploaded_by: null, preview: null,
      auto_status: 'applied', auto_reasons: [], review_flags: [{ entry_id: 2, code: 'fewer_laps' }],
    }
    show({ 'GET /api/rounds/9/imports': () => json(200, [blocked, published]) })
    expect(await screen.findByText('Espera a un admin')).toBeInTheDocument()
    expect(screen.getByText('El lastre o el restrictor del archivo no es el asignado.')).toBeInTheDocument()
    expect(screen.getByText('La fecha ya tiene resultado: un admin decide si lo cambia.')).toBeInTheDocument()
    expect(screen.getByText('Publicado por el colector')).toBeInTheDocument()
    expect(screen.getByText(/Vice hizo menos vueltas que el ganador/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Marcar DNF' })).toBeInTheDocument()
  })
})
