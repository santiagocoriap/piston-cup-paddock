import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../test-utils'
import { DriverScriptCard } from './DriverScriptCard'

afterEach(() => vi.restoreAllMocks())

const setup = (code: string) => ({
  script_url: 'https://paddock.test/api/script/paddock.lua',
  race_code: code,
  created_at: '2026-10-14T20:00:00Z',
  csp_section: `[SCRIPT_1]\nSCRIPT = 'https://paddock.test/api/script/paddock.lua'\nraceCode = '${code}'\n`,
})

describe('DriverScriptCard', () => {
  it('shows the text for the server and makes a new code', async () => {
    const calls = mockApi({
      'GET /api/championships/1/script': () => json(200, setup('old-code')),
      'POST /api/championships/1/script/code': () => json(200, setup('new-code')),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage(<DriverScriptCard championshipId={1} />, { path: '/', url: '/' })
    expect(await screen.findByText(/raceCode = 'old-code'/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Hacer un código nuevo' }))
    expect(await screen.findByText(/raceCode = 'new-code'/)).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'POST /api/championships/1/script/code')).toBe(true)
  })
})
