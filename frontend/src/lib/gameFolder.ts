/** Read the cars and the tracks of an Assetto Corsa folder in the browser, and pack the files
 * of the chosen ones into a ZIP with the paths of the content folder. The browser reads only
 * the small files: the JSON data, the badges, the maps, and one preview for each car. */
import { zipSync } from 'fflate'

/** The part of the File System Access API that the import uses. */
export type DirHandle = {
  kind: 'directory'
  name: string
  values: () => AsyncIterable<DirHandle | FileHandle>
  getDirectoryHandle: (name: string) => Promise<DirHandle>
  getFileHandle: (name: string) => Promise<FileHandle>
}
export type FileHandle = { kind: 'file'; name: string; getFile: () => Promise<File> }

export type GameCar = { key: string; name: string; brand: string; dir: DirHandle }
export type GameLayout = { key: string; name: string; dir: DirHandle }
export type GameTrack = { key: string; name: string; layouts: GameLayout[] }

const KEY = /^[A-Za-z0-9_.-]{1,100}$/

async function child(dir: DirHandle, name: string): Promise<DirHandle | null> {
  try {
    return await dir.getDirectoryHandle(name)
  } catch {
    return null
  }
}

async function file(dir: DirHandle, name: string): Promise<File | null> {
  try {
    return await (await dir.getFileHandle(name)).getFile()
  } catch {
    return null
  }
}

async function fileEntries(dir: DirHandle): Promise<FileHandle[]> {
  const found: FileHandle[] = []
  for await (const entry of dir.values()) if (entry.kind === 'file') found.push(entry)
  return found
}

async function folders(dir: DirHandle): Promise<DirHandle[]> {
  const found: DirHandle[] = []
  for await (const entry of dir.values()) if (entry.kind === 'directory') found.push(entry)
  return found.sort((a, b) => a.name.localeCompare(b.name))
}

type Node = { dirs: Map<string, Node>; files: Map<string, File> }

/** A folder from a file input with webkitdirectory (Firefox has no showDirectoryPicker). The
 * input gives every file with its path in the folder. This makes the same handle as the
 * picker, so the scan and the pack work the same way. */
export function fromFileList(files: Iterable<File>): DirHandle | null {
  const root: Node = { dirs: new Map(), files: new Map() }
  let rootName = ''
  for (const one of files) {
    const parts = (one.webkitRelativePath || one.name).split('/')
    rootName ||= parts[0]
    let node = root
    for (const part of parts.slice(1, -1)) {
      let next = node.dirs.get(part)
      if (!next) {
        next = { dirs: new Map(), files: new Map() }
        node.dirs.set(part, next)
      }
      node = next
    }
    node.files.set(parts[parts.length - 1], one)
  }
  return rootName ? virtual(rootName, root) : null
}

function virtual(name: string, node: Node): DirHandle {
  const fileHandle = (fileName: string, one: File): FileHandle => ({ kind: 'file', name: fileName, getFile: async () => one })
  return {
    kind: 'directory',
    name,
    values: async function* () {
      for (const [dirName, dir] of node.dirs) yield virtual(dirName, dir)
      for (const [fileName, one] of node.files) yield fileHandle(fileName, one)
    },
    getDirectoryHandle: async (child) => {
      const dir = node.dirs.get(child)
      if (!dir) throw new Error('not found')
      return virtual(child, dir)
    },
    getFileHandle: async (child) => {
      const one = node.files.get(child)
      if (!one) throw new Error('not found')
      return fileHandle(child, one)
    },
  }
}

/** The game writes loose JSON: a BOM, raw line breaks, sometimes trailing commas. */
export function looseJson(text: string): Record<string, unknown> {
  const clean = text.replace(/^﻿/, '')
  try {
    const value = JSON.parse(clean.replace(/[\r\n\t]+/g, ' ').replace(/,\s*([}\]])/g, '$1'))
    return value && typeof value === 'object' ? value : {}
  } catch {
    const result: Record<string, string> = {}
    for (const key of ['name', 'brand']) {
      const match = clean.match(new RegExp(`"${key}"\\s*:\\s*"([^"]*)"`))
      if (match) result[key] = match[1]
    }
    return result
  }
}

async function json(dir: DirHandle, name: string): Promise<Record<string, unknown> | null> {
  const found = await file(dir, name)
  return found ? looseJson(await found.text()) : null
}

/** The content folder: the folder itself, or "content" inside the assettocorsa folder. */
export async function contentFolder(picked: DirHandle): Promise<DirHandle | null> {
  if ((await child(picked, 'cars')) || (await child(picked, 'tracks'))) return picked
  return child(picked, 'content')
}

/** The shared start of the layout names, for the track name. */
export function commonName(names: string[]): string {
  if (names.length === 1) return names[0]
  const words = names.map((name) => name.split(/\s+/))
  const shared: string[] = []
  for (let i = 0; i < Math.min(...words.map((w) => w.length)); i++) {
    const word = words[0][i]
    if (!words.every((w) => w[i]?.toLowerCase() === word.toLowerCase())) break
    shared.push(word)
  }
  return shared.join(' ').replace(/[\s\-·]+$/, '')
}

export async function scanCars(content: DirHandle, onCount?: (n: number) => void): Promise<GameCar[]> {
  const carsDir = await child(content, 'cars')
  if (!carsDir) return []
  const cars: GameCar[] = []
  for (const dir of await folders(carsDir)) {
    if (!KEY.test(dir.name)) continue
    const ui = await child(dir, 'ui')
    const info = ui ? await json(ui, 'ui_car.json') : null
    if (!info) continue
    cars.push({ key: dir.name, name: String(info.name || dir.name).trim(), brand: String(info.brand || ''), dir })
    onCount?.(cars.length)
  }
  return cars
}

export async function scanTracks(content: DirHandle, onCount?: (n: number) => void): Promise<GameTrack[]> {
  const tracksDir = await child(content, 'tracks')
  if (!tracksDir) return []
  const tracks: GameTrack[] = []
  for (const dir of await folders(tracksDir)) {
    if (!KEY.test(dir.name)) continue
    const ui = await child(dir, 'ui')
    if (!ui) continue
    const layouts: GameLayout[] = []
    const single = await json(ui, 'ui_track.json')
    if (single) layouts.push({ key: '', name: String(single.name || dir.name).trim(), dir: ui })
    for (const sub of await folders(ui)) {
      if (!KEY.test(sub.name)) continue
      const info = await json(sub, 'ui_track.json')
      if (info) layouts.push({ key: sub.name, name: String(info.name || sub.name).trim(), dir: sub })
    }
    if (layouts.length === 0) continue
    tracks.push({ key: dir.name, name: commonName(layouts.map((l) => l.name)) || dir.name, layouts })
    onCount?.(tracks.length)
  }
  return tracks
}

async function bytes(dir: DirHandle, name: string, limit = 5 * 1024 * 1024): Promise<Uint8Array | null> {
  const found = await file(dir, name)
  return found && found.size <= limit ? new Uint8Array(await found.arrayBuffer()) : null
}

const SKIN_SIDE = 640
/** The largest skin picture that is sent as it is, when the browser cannot make it smaller. */
const SKIN_AS_IS = 400 * 1024
const DATA_FILE = /\.(ini|lut|rto)$/i

/** A skin preview is 1920x1080 and a car can have 30 of them. The server keeps only a small
 * picture, so the browser makes it small before it sends it. */
export async function shrinkPicture(data: Uint8Array): Promise<Uint8Array | null> {
  try {
    const bitmap = await createImageBitmap(new Blob([data as Uint8Array<ArrayBuffer>]))
    const scale = Math.min(1, SKIN_SIDE / Math.max(bitmap.width, bitmap.height))
    const canvas = new OffscreenCanvas(Math.round(bitmap.width * scale), Math.round(bitmap.height * scale))
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()
    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.82 })
    return new Uint8Array(await blob.arrayBuffer())
  } catch {
    // No canvas in this browser: send a small picture as it is, and skip a large one.
    return data.length <= SKIN_AS_IS ? data : null
  }
}

/** A ZIP with the files of the chosen cars and tracks, for POST /api/catalog/game-import.
 * A car sends its data (data.acd, or the loose files of an unpacked data folder), the file that
 * marks a DLC car, and for each skin its name file and a small picture. */
export async function packSelection(cars: GameCar[], tracks: GameTrack[]): Promise<Blob> {
  const files: Record<string, Uint8Array> = {}
  const put = (path: string, data: Uint8Array | null) => {
    if (data) files[path] = data
  }
  for (const car of cars) {
    const ui = await child(car.dir, 'ui')
    if (ui) {
      put(`cars/${car.key}/ui/ui_car.json`, await bytes(ui, 'ui_car.json'))
      put(`cars/${car.key}/ui/dlc_ui_car.json`, await bytes(ui, 'dlc_ui_car.json'))
      put(`cars/${car.key}/ui/badge.png`, await bytes(ui, 'badge.png'))
    }
    const data = await child(car.dir, 'data')
    if (data) {
      for (const entry of await fileEntries(data)) {
        if (DATA_FILE.test(entry.name)) put(`cars/${car.key}/data/${entry.name}`, await bytes(data, entry.name, 2 * 1024 * 1024))
      }
    } else {
      put(`cars/${car.key}/data.acd`, await bytes(car.dir, 'data.acd', 20 * 1024 * 1024))
    }
    // Every skin: its names and a small picture. The first picture is also the car picture.
    const skins = await child(car.dir, 'skins')
    let first = true
    for (const skin of skins ? await folders(skins) : []) {
      put(`cars/${car.key}/skins/${skin.name}/ui_skin.json`, await bytes(skin, 'ui_skin.json'))
      const raw = await bytes(skin, 'preview.jpg')
      const small = raw ? await shrinkPicture(raw) : null
      put(`cars/${car.key}/skins/${skin.name}/preview.jpg`, small)
      if (small && first) {
        put(`cars/${car.key}/preview.jpg`, small)
        first = false
      }
    }
  }
  for (const track of tracks) {
    for (const layout of track.layouts) {
      const base = layout.key ? `tracks/${track.key}/ui/${layout.key}` : `tracks/${track.key}/ui`
      for (const name of ['ui_track.json', 'outline.png', 'preview.png']) {
        put(`${base}/${name}`, await bytes(layout.dir, name))
      }
    }
  }
  // Pictures are compressed already: store them as they are.
  const zipped = zipSync(files, { level: 0 })
  return new Blob([zipped as Uint8Array<ArrayBuffer>], { type: 'application/zip' })
}
