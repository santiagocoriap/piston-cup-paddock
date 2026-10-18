import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DirHandle, FileHandle } from '../../lib/gameFolder'
import { renderPage } from '../../test-utils'
import { GameImportDialog } from './GameImportDialog'

afterEach(() => {
  vi.restoreAllMocks()
  delete (window as unknown as { showDirectoryPicker?: unknown }).showDirectoryPicker
})

type Tree = { [name: string]: Tree | string }

function folder(name: string, tree: Tree): DirHandle {
  const file = (child: string, text: string): FileHandle => ({ kind: 'file', name: child, getFile: async () => new File([text], child) })
  return {
    kind: 'directory',
    name,
    values: async function* () {
      for (const [child, value] of Object.entries(tree)) yield typeof value === 'string' ? file(child, value) : folder(child, value)
    },
    getDirectoryHandle: async (child) => {
      const value = tree[child]
      if (!value || typeof value === 'string') throw new Error('not found')
      return folder(child, value)
    },
    getFileHandle: async (child) => {
      const value = tree[child]
      if (typeof value !== 'string') throw new Error('not found')
      return file(child, value)
    },
  }
}

describe('GameImportDialog', () => {
  it('lists the weather presets of the folder in the Clima tab', async () => {
    const game = folder('assettocorsa', {
      content: {
        cars: { x: { ui: { 'ui_car.json': '{"name": "X"}' } } },
        tracks: {},
        weather: {
          '3_clear': { 'weather.ini': '[LAUNCHER]\nNAME=Clear ; menu name\n' },
          '1_heavy_fog': { 'weather.ini': '[LAUNCHER]\nNAME=Heavy Fog\n' },
        },
      },
    })
    ;(window as unknown as { showDirectoryPicker: () => Promise<DirHandle> }).showDirectoryPicker = async () => game
    renderPage(<GameImportDialog open onClose={() => undefined} onImported={() => undefined} knownCars={[]} knownTracks={[]} knownWeather={[]} />, {
      path: '/admin/catalog',
      url: '/admin/catalog',
    })
    await userEvent.click(screen.getByRole('button', { name: 'Elegir la carpeta content' }))
    const tab = await screen.findByRole('tab', { name: '2 climas' })
    await userEvent.click(tab)
    expect(await screen.findByText('Clear')).toBeInTheDocument()
    expect(screen.getByText('Heavy Fog')).toBeInTheDocument()
  })

  it('says why no weather was found when the folder has none', async () => {
    const game = folder('assettocorsa', { content: { cars: { x: { ui: { 'ui_car.json': '{"name": "X"}' } } }, tracks: {} } })
    ;(window as unknown as { showDirectoryPicker: () => Promise<DirHandle> }).showDirectoryPicker = async () => game
    renderPage(<GameImportDialog open onClose={() => undefined} onImported={() => undefined} knownCars={[]} knownTracks={[]} />, {
      path: '/admin/catalog',
      url: '/admin/catalog',
    })
    await userEvent.click(screen.getByRole('button', { name: 'Elegir la carpeta content' }))
    await userEvent.click(await screen.findByRole('tab', { name: '0 climas' }))
    expect(await screen.findByText(/no hay content\/weather/)).toBeInTheDocument()
  })

  it('reads the weather presets from the weather folder chosen with a file input', async () => {
    // Edge hides .ini files from the folder picker: the picked folder lists no files.
    const game = folder('assettocorsa', {
      content: { cars: { x: { ui: { 'ui_car.json': '{"name": "X"}' } } }, tracks: {}, weather: { '3_clear': {}, '1_heavy_fog': {} } },
    })
    ;(window as unknown as { showDirectoryPicker: () => Promise<DirHandle> }).showDirectoryPicker = async () => game
    const { container } = renderPage(
      <GameImportDialog open onClose={() => undefined} onImported={() => undefined} knownCars={[]} knownTracks={[]} />,
      { path: '/admin/catalog', url: '/admin/catalog' },
    )
    await userEvent.click(screen.getByRole('button', { name: 'Elegir la carpeta content' }))
    await userEvent.click(await screen.findByRole('tab', { name: '0 climas' }))
    expect(await screen.findByText(/ninguna tiene weather.ini/)).toBeInTheDocument()
    const file = (path: string, text: string) => {
      const one = new File([text], path.split('/').pop()!)
      Object.defineProperty(one, 'webkitRelativePath', { value: path })
      return one
    }
    const input = container.ownerDocument.querySelectorAll('input[type="file"]')[1] as HTMLInputElement
    await userEvent.upload(input, [
      file('weather/3_clear/weather.ini', '[LAUNCHER]\nNAME=Clear ; menu\n'),
      file('weather/1_heavy_fog/weather.ini', '[LAUNCHER]\nNAME=Heavy Fog\n'),
    ])
    expect(await screen.findByRole('tab', { name: '2 climas' })).toBeInTheDocument()
    expect(await screen.findByText('Clear')).toBeInTheDocument()
    expect(screen.getByText('Heavy Fog')).toBeInTheDocument()
  })
})
