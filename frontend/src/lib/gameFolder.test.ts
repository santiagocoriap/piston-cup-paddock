import { unzipSync, strFromU8 } from 'fflate'
import { describe, expect, it } from 'vitest'
import { commonName, contentFolder, fromFileList, looseJson, packSelection, scanCars, scanTracks, scanWeather, type DirHandle, type FileHandle } from './gameFolder'

type Tree = { [name: string]: Tree | string }

/** A fake folder for the File System Access API. */
function folder(name: string, tree: Tree): DirHandle {
  const entries = () =>
    Object.entries(tree).map(([child, value]) => (typeof value === 'string' ? fileOf(child, value) : folder(child, value)))
  return {
    kind: 'directory',
    name,
    values: async function* () {
      yield* entries()
    },
    getDirectoryHandle: async (child) => {
      const value = tree[child]
      if (!value || typeof value === 'string') throw new Error('not found')
      return folder(child, value)
    },
    getFileHandle: async (child) => {
      const value = tree[child]
      if (typeof value !== 'string') throw new Error('not found')
      return fileOf(child, value)
    },
  }
}

function fileOf(name: string, text: string): FileHandle {
  return { kind: 'file', name, getFile: async () => new File([text], name) }
}

const game = folder('assettocorsa', {
  content: {
    cars: {
      bmw_m3_e30: { ui: { 'ui_car.json': '\uFEFF{"name": "BMW M3 E30",\n "brand": "BMW",}', 'badge.png': 'png' }, skins: { red: { 'preview.jpg': 'jpg' } } },
      'bad name': { ui: { 'ui_car.json': '{"name": "x"}' } },
      no_ui: {},
    },
    tracks: {
      ks_highlands: { ui: { layout_long: { 'ui_track.json': '{"name": "Highlands Long"}', 'outline.png': 'o' }, layout_short: { 'ui_track.json': '{"name": "Highlands Short"}' } } },
      magione: { ui: { 'ui_track.json': '{"name": "Magione"}', 'preview.png': 'p' } },
    },
  },
})

describe('gameFolder', () => {
  it('finds the content folder, the cars, and the tracks', async () => {
    const content = (await contentFolder(game))!
    expect(content.name).toBe('content')
    const cars = await scanCars(content)
    expect(cars.map((c) => [c.key, c.name, c.brand])).toEqual([['bmw_m3_e30', 'BMW M3 E30', 'BMW']])
    const tracks = await scanTracks(content)
    expect(tracks.map((tr) => [tr.key, tr.name, tr.layouts.map((l) => l.key)])).toEqual([
      ['ks_highlands', 'Highlands', ['layout_long', 'layout_short']],
      ['magione', 'Magione', ['']],
    ])
  })

  it('packs the files of the chosen items with the content paths', async () => {
    const content = (await contentFolder(game))!
    const zip = await packSelection(await scanCars(content), (await scanTracks(content)).slice(1))
    const files = unzipSync(new Uint8Array(await zip.arrayBuffer()))
    expect(Object.keys(files).sort()).toEqual([
      'cars/bmw_m3_e30/preview.jpg',
      'cars/bmw_m3_e30/skins/red/preview.jpg',
      'cars/bmw_m3_e30/ui/badge.png',
      'cars/bmw_m3_e30/ui/ui_car.json',
      'tracks/magione/ui/preview.png',
      'tracks/magione/ui/ui_track.json',
    ])
    expect(strFromU8(files['tracks/magione/ui/preview.png'])).toBe('p')
  })

  it('packs the data, the DLC marker, and every skin of a car', async () => {
    const dlc = folder('assettocorsa', {
      content: {
        cars: {
          ks_ferrari_488_gt3: {
            'data.acd': 'acd',
            ui: { 'ui_car.json': '{"name": "Ferrari 488 GT3"}', 'dlc_ui_car.json': '{"url": "http://store.steampowered.com/app/1"}' },
            skins: { '00 red': { 'ui_skin.json': '{"skinname": "Red"}', 'preview.jpg': 'a' }, blue: { 'ui_skin.json': '{}' } },
          },
          trr_unpacked: {
            data: { 'tyres.ini': '[FRONT]', 'power.lut': '0|0', 'car.kn5': 'no' },
            ui: { 'ui_car.json': '{"name": "Unpacked"}' },
          },
        },
      },
    })
    const content = (await contentFolder(dlc))!
    const zip = await packSelection(await scanCars(content), [])
    const files = unzipSync(new Uint8Array(await zip.arrayBuffer()))
    expect(Object.keys(files).sort()).toEqual([
      'cars/ks_ferrari_488_gt3/data.acd',
      'cars/ks_ferrari_488_gt3/preview.jpg',
      'cars/ks_ferrari_488_gt3/skins/00 red/preview.jpg',
      'cars/ks_ferrari_488_gt3/skins/00 red/ui_skin.json',
      'cars/ks_ferrari_488_gt3/skins/blue/ui_skin.json',
      'cars/ks_ferrari_488_gt3/ui/dlc_ui_car.json',
      'cars/ks_ferrari_488_gt3/ui/ui_car.json',
      'cars/trr_unpacked/data/power.lut',
      'cars/trr_unpacked/data/tyres.ini',
      'cars/trr_unpacked/ui/ui_car.json',
    ])
  })

  it('reads loose JSON and shared names', () => {
    expect(looseJson('{"name": "A",\n}')).toEqual({ name: 'A' })
    expect(looseJson('{"name": "B" "broken"')).toEqual({ name: 'B' })
    expect(commonName(['Spa GP', 'Spa Short'])).toBe('Spa')
  })

  it('reads a folder from a Firefox file input', async () => {
    const pick = (path: string, text: string) => {
      const one = new File([text], path.split('/').pop()!)
      Object.defineProperty(one, 'webkitRelativePath', { value: path })
      return one
    }
    const root = fromFileList([
      pick('content/cars/bmw_m3_e30/ui/ui_car.json', '{"name": "BMW M3 E30"}'),
      pick('content/cars/bmw_m3_e30/skins/red/preview.jpg', 'jpg'),
      pick('content/tracks/magione/ui/ui_track.json', '{"name": "Magione"}'),
    ])!
    expect(root.name).toBe('content')
    const content = (await contentFolder(root))!
    expect((await scanCars(content)).map((c) => c.name)).toEqual(['BMW M3 E30'])
    expect((await scanTracks(content)).map((t) => t.key)).toEqual(['magione'])
  })
})

describe('weather presets', () => {
  const withWeather = folder('assettocorsa', {
    content: {
      weather: {
        '3_clear': { 'weather.ini': '[CLOUDS]\nCOVER=0.9 ; clouds\n[LAUNCHER]\nNAME=Clear ; name in the launcher menus\n', 'colorCurves.ini': 'x' },
        sol_35_rain: { 'weather.ini': '[LAUNCHER]\r\nNAME=Rain (Sol)\r\n', 'preview.jpg': 'jpg' },
        'no ini': { 'colorCurves.ini': 'x' },
        'readme_weather.txt': 'text',
      },
    },
  })

  it('finds the presets with their names, without the comment after the name', async () => {
    const content = (await contentFolder(withWeather))!
    const found = await scanWeather(content)
    expect(found.map((w) => [w.key, w.name])).toEqual([
      ['3_clear', 'Clear'],
      ['sol_35_rain', 'Rain (Sol)'],
    ])
  })

  it('packs weather.ini and the preview of the chosen presets', async () => {
    const content = (await contentFolder(withWeather))!
    const zip = await packSelection([], [], await scanWeather(content))
    const files = unzipSync(new Uint8Array(await zip.arrayBuffer()))
    expect(Object.keys(files).sort()).toEqual([
      'weather/3_clear/weather.ini',
      'weather/sol_35_rain/preview.jpg',
      'weather/sol_35_rain/weather.ini',
    ])
  })
})
