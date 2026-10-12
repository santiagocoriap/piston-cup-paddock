import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'
import { SessionProvider } from '../SessionProvider'
import { DRIVER, json, mockApi } from '../test-utils'
import { AccountPage } from './AccountPage'

afterEach(async () => {
  vi.restoreAllMocks()
  await i18n.changeLanguage('es')
})

describe('AccountPage', () => {
  it('changes the language and the timezone', async () => {
    const updated = { ...DRIVER, language: 'en', timezone: 'Europe/Madrid' }
    const calls = mockApi({ 'PATCH /api/auth/me': () => json(200, updated) })
    const onMeChange = vi.fn()
    render(
      <SessionProvider me={DRIVER} onMeChange={onMeChange}>
        <MemoryRouter>
          <AccountPage />
        </MemoryRouter>
      </SessionProvider>,
    )
    await userEvent.selectOptions(screen.getByLabelText('Idioma'), 'en')
    await userEvent.selectOptions(screen.getByLabelText('Zona horaria'), 'Europe/Madrid')
    const settings = screen.getByRole('form', { name: 'Mi cuenta' })
    await userEvent.click(within(settings).getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByRole('status')).toHaveTextContent('The changes are saved.')
    expect(calls.find((c) => c.key === 'PATCH /api/auth/me')!.body).toEqual({
      language: 'en',
      timezone: 'Europe/Madrid',
    })
    expect(onMeChange).toHaveBeenCalledWith(updated)
  })
})
