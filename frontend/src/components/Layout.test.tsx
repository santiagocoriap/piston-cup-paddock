import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, DRIVER, json, mockApi, renderPage } from '../test-utils'
import { Layout } from './Layout'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  delete document.documentElement.dataset.theme
})

const noNotes = () => json(200, { unread: 0, items: [] })

describe('Layout side menu', () => {
  it('makes the menu a rail of icons, and remembers the choice', async () => {
    mockApi({ 'GET /api/me/notifications': noNotes })
    const { container, unmount } = renderPage(<Layout onSignOut={() => {}} />, { path: '/', url: '/', me: DRIVER })
    const toggle = screen.getByRole('button', { name: 'Achicar el menú' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(toggle)
    expect(container.querySelector('.app')).toHaveClass('side-rail')
    // The links stay in the rail, with their names for screen readers.
    expect(screen.getByRole('link', { name: 'Récords' })).toHaveAttribute('data-label', 'Récords')
    unmount()
    renderPage(<Layout onSignOut={() => {}} />, { path: '/', url: '/', me: DRIVER })
    expect(screen.getByRole('button', { name: 'Agrandar el menú' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('shows the pending counts on the admin items', async () => {
    mockApi({
      'GET /api/me/notifications': noNotes,
      'GET /api/pending': () =>
        json(200, [
          { kind: 'results', count: 2, items: [] },
          { kind: 'protests', count: 1, items: [] },
          { kind: 'accounts', count: 3, items: [] },
          { kind: 'images', count: 5, items: [] },
        ]),
    })
    renderPage(<Layout onSignOut={() => {}} />, { path: '/', url: '/', me: ADMIN })
    expect(await screen.findByRole('link', { name: 'Inicio, 3 pendientes' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cuentas, 3 pendientes' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Pistas y autos, 5 pendientes' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ligas' })).toBeInTheDocument()
  })

  it('shows a short admin tag with the full sentence for screen readers', async () => {
    mockApi({ 'GET /api/me/notifications': noNotes, 'GET /api/pending': () => json(200, []) })
    renderPage(<Layout onSignOut={() => {}} />, { path: '/', url: '/', me: ADMIN })
    const note = await screen.findByRole('note')
    expect(within(note).getByText('Modo admin').closest('.mode-tag')).toHaveAttribute('title', 'Los cambios afectan a toda la liga y quedan en el historial.')
  })
})

describe('Layout account menu', () => {
  it('opens the account menu with the theme switch and the sign out', async () => {
    mockApi({ 'GET /api/me/notifications': noNotes })
    const signOut = vi.fn()
    renderPage(<Layout onSignOut={signOut} />, { path: '/', url: '/', me: DRIVER })
    const [sideMenu] = screen.getAllByRole('button', { name: 'Menú de racer' })
    await userEvent.click(sideMenu)
    const menu = screen.getByRole('menu', { name: 'Menú de racer' })
    expect(within(menu).getByText('Piloto')).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Mi cuenta' })).toHaveAttribute('href', '/account')
    await userEvent.click(within(menu).getByRole('menuitem', { name: 'Tema de día' }))
    expect(document.documentElement.dataset.theme).toBe('dia')
    expect(localStorage.getItem('paddock.theme')).toBe('dia')
    expect(within(menu).getByRole('menuitem', { name: 'Tema de noche' })).toBeInTheDocument()
    await userEvent.click(within(menu).getByRole('menuitem', { name: 'Cerrar sesión' }))
    expect(signOut).toHaveBeenCalled()
    // The header has no separate sign-out icon.
    expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).not.toBeInTheDocument()
  })

  it('closes the account menu with Escape', async () => {
    mockApi({ 'GET /api/me/notifications': noNotes })
    renderPage(<Layout onSignOut={() => {}} />, { path: '/', url: '/', me: DRIVER })
    await userEvent.click(screen.getAllByRole('button', { name: 'Menú de racer' })[0])
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})

describe('Layout search', () => {
  it('opens with Ctrl+K, searches, and opens a result with Enter', async () => {
    mockApi({
      'GET /api/me/notifications': noNotes,
      'GET /api/search': () =>
        json(200, [
          { kind: 'round', label: 'Highlands · Long', detail: 'LMDh 2026', path: '/rounds/9', number: 3 },
          { kind: 'driver', label: 'Ana Highlander', detail: '', path: '/drivers/4', number: null },
        ]),
    })
    renderPage(<Layout onSignOut={() => {}} />, { path: '*', url: '/', me: DRIVER })
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const dialog = screen.getByRole('dialog', { name: 'Buscar' })
    expect(dialog).toHaveAttribute('open')
    const box = within(dialog).getByRole('combobox', { name: 'Buscar' })
    await userEvent.type(box, 'highl')
    expect(await within(dialog).findByRole('option', { name: /Fecha 3 · Highlands · Long/ })).toBeInTheDocument()
    expect(within(dialog).getByRole('option', { name: /Ana Highlander/ })).toBeInTheDocument()
    await userEvent.keyboard('{Enter}')
    expect(dialog).not.toHaveAttribute('open')
  })

  it('finds pages without the server', async () => {
    mockApi({ 'GET /api/me/notifications': noNotes })
    renderPage(<Layout onSignOut={() => {}} />, { path: '/', url: '/', me: DRIVER })
    await userEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    await userEvent.type(screen.getByRole('combobox', { name: 'Buscar' }), 'réc')
    expect(screen.getByRole('option', { name: 'Récords' })).toHaveAttribute('aria-selected', 'true')
  })
})

describe('Layout notifications', () => {
  it('groups the notifications by day and filters the unread ones', async () => {
    const now = new Date().toISOString()
    const read = vi.fn(() => json(200, { unread: 0, items: [] }))
    mockApi({
      'GET /api/me/notifications': () =>
        json(200, {
          unread: 1,
          items: [
            { id: 1, kind: 'ballot.open', params: { title: 'Pistas 2027' }, link: '/ballots/1', created_at: now, read: false },
            { id: 2, kind: 'ballot.open', params: { title: 'Clases' }, link: '/ballots/2', created_at: '2026-01-02T12:00:00Z', read: true },
          ],
        }),
      'POST /api/me/notifications/read': read,
    })
    renderPage(<Layout onSignOut={() => {}} />, { path: '/', url: '/', me: DRIVER })
    await userEvent.click(await screen.findByRole('button', { name: /notificaci/i }))
    const panel = screen.getByRole('dialog', { name: /notificaciones/i })
    expect(within(panel).getByRole('region', { name: 'Hoy' })).toBeInTheDocument()
    expect(within(panel).getAllByRole('listitem')).toHaveLength(2)
    await userEvent.click(within(panel).getByRole('button', { name: /Sin leer/ }))
    expect(within(panel).getAllByRole('listitem')).toHaveLength(1)
    await userEvent.click(within(panel).getByRole('button', { name: 'Marcar todo como leído' }))
    expect(read).toHaveBeenCalled()
  })
})
