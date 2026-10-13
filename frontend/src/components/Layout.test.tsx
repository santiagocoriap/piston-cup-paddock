import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DRIVER, json, mockApi, renderPage } from '../test-utils'
import { Layout } from './Layout'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('Layout', () => {
  it('hides and shows the side menu, and remembers the choice', async () => {
    mockApi({ 'GET /api/me/notifications': () => json(200, { unread: 0, items: [] }) })
    const { container, unmount } = renderPage(<Layout onSignOut={() => {}} />, { path: '/', url: '/', me: DRIVER })
    const toggle = screen.getByRole('button', { name: 'Ocultar el menú lateral' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(toggle)
    expect(container.querySelector('.app')).toHaveClass('side-hidden')
    expect(screen.getByRole('button', { name: 'Mostrar el menú lateral' })).toHaveAttribute('aria-expanded', 'false')
    unmount()
    renderPage(<Layout onSignOut={() => {}} />, { path: '/', url: '/', me: DRIVER })
    expect(screen.getByRole('button', { name: 'Mostrar el menú lateral' })).toBeInTheDocument()
  })
})
