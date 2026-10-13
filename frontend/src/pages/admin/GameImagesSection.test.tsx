import { fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, mockApi, renderPage } from '../../test-utils'
import { GameImagesSection } from './GameImagesSection'

afterEach(() => vi.restoreAllMocks())

describe('GameImagesSection', () => {
  it('uploads the ZIP and shows what it imported and what is missing', async () => {
    const onImported = vi.fn()
    mockApi({
      'POST /api/catalog/game-images': () =>
        json(200, { layouts: ['ks_highlands/layout_long'], cars: ['acura'], missing_layouts: ['magione'], missing_cars: [] }),
    })
    renderPage(<GameImagesSection onImported={onImported} />, { path: '/', url: '/' })
    const zip = new File(['PK'], 'paddock-images.zip', { type: 'application/zip' })
    const input = screen.getByLabelText('Archivo ZIP') as HTMLInputElement
    await userEvent.upload(input, zip)
    fireEvent.submit(input.form!)
    expect(await screen.findByText('Listo: 1 trazados y 1 autos con imágenes.')).toBeInTheDocument()
    expect(screen.getByText('1 sin archivos en el ZIP')).toBeInTheDocument()
    expect(onImported).toHaveBeenCalled()
  })

  it('explains a refused file', async () => {
    mockApi({ 'POST /api/catalog/game-images': () => json(400, { detail: 'bad_zip' }) })
    renderPage(<GameImagesSection onImported={() => {}} />, { path: '/', url: '/' })
    const input = screen.getByLabelText('Archivo ZIP') as HTMLInputElement
    await userEvent.upload(input, new File(['x'], 'x.zip', { type: 'application/zip' }))
    fireEvent.submit(input.form!)
    expect(await screen.findByRole('alert')).toHaveTextContent('El archivo no es un ZIP válido.')
  })
})
