import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderPage } from '../test-utils'
import { Breadcrumbs } from './Breadcrumbs'

describe('Breadcrumbs', () => {
  it('starts at Inicio, links each level, and marks this page', async () => {
    renderPage(
      <Breadcrumbs items={[{ label: 'Demo LMDh', to: '/championships/1' }, { label: '2026', to: '/seasons/4' }, { label: 'Fecha 1' }]} />,
      { path: '/rounds/9', url: '/rounds/9' },
    )
    const nav = await screen.findByRole('navigation', { name: 'Ruta de navegación' })
    expect(within(nav).getAllByRole('link').map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['Inicio', '/'],
      ['Demo LMDh', '/championships/1'],
      ['2026', '/seasons/4'],
    ])
    expect(within(nav).getByText('Fecha 1')).toHaveAttribute('aria-current', 'page')
  })
})
