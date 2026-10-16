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

  it('refuses a file that is not a ZIP and shows the chosen ZIP', async () => {
    mockApi({})
    renderPage(<GameImagesSection onImported={vi.fn()} />, { path: '/', url: '/' })
    const input = screen.getByLabelText('Archivo ZIP') as HTMLInputElement
    await userEvent.upload(input, new File(['x'], 'notes.txt', { type: 'text/plain' }), { applyAccept: false })
    expect(screen.getByRole('alert')).toHaveTextContent('El archivo tiene que ser un .zip.')
    await userEvent.upload(input, new File(['PK'], 'paddock-images.zip', { type: 'application/zip' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('paddock-images.zip · 1 KB')).toBeInTheDocument()
  })

  it('copies the command and marks the step as done', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderPage(<GameImagesSection onImported={vi.fn()} />, { path: '/', url: '/' })
    await user.click(screen.getByRole('button', { name: 'Copiar el comando' }))
    expect(await navigator.clipboard.readText()).toBe('python tools/pack_game_images.py --needed paddock-needed.json')
    expect(screen.getByRole('heading', { name: /^Correr el script\s*·\s*Hecho$/ })).toBeInTheDocument()
  })

  it('marks the upload step as done after an upload', async () => {
    mockApi({
      'POST /api/catalog/game-images': () => json(200, { layouts: [], cars: [], missing_layouts: [], missing_cars: [] }),
    })
    renderPage(<GameImagesSection onImported={vi.fn()} />, { path: '/', url: '/' })
    expect(screen.getByRole('heading', { name: /^Subir el ZIP$/ })).toBeInTheDocument()
    const input = screen.getByLabelText('Archivo ZIP') as HTMLInputElement
    await userEvent.upload(input, new File(['PK'], 'paddock-images.zip', { type: 'application/zip' }))
    fireEvent.submit(input.form!)
    expect(await screen.findByRole('heading', { name: /^Subir el ZIP\s*·\s*Hecho$/ })).toBeInTheDocument()
  })
})
