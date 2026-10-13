// Outline icons drawn on a 24px grid with a 1.85 stroke, in the style of Lucide.
const PATHS = {
  home: ['M3 10.5 12 3l9 7.5', 'M5 9.5V21h14V9.5', 'M10 21v-6h4v6'],
  trophy: ['M8 21h8', 'M12 17v4', 'M7 4h10v5a5 5 0 0 1-10 0z', 'M7 6H4a3 3 0 0 0 3 4', 'M17 6h3a3 3 0 0 1-3 4'],
  timer: ['M10 2h4', 'M12 14l3-3', 'C12 14 8'],
  user: ['C12 8 4', 'M4 21a8 8 0 0 1 16 0'],
  users: ['C9 8 4', 'M2 21a7 7 0 0 1 14 0', 'M16 4a4 4 0 0 1 0 8', 'M22 21a7 7 0 0 0-4-6.3'],
  shield: ['M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z'],
  flag: ['M4 22V4', 'M4 15s1.5-1 4-1 4.5 2 8 2 4-1 4-1V4s-1 1-4 1-5-2-8-2-4 1-4 1'],
  map: ['M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z', 'M9 4v14', 'M15 6v14'],
  layers: ['m12 3 9 5-9 5-9-5z', 'm3 13 9 5 9-5'],
  history: ['M3 12a9 9 0 1 0 3-6.7L3 8', 'M3 3v5h5', 'M12 7v5l3 2'],
  bell: ['M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9', 'M10.3 21a1.94 1.94 0 0 0 3.4 0'],
  logout: ['M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4', 'm16 17 5-5-5-5', 'M21 12H9'],
  help: ['C12 12 10', 'M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3', 'M12 17h.01'],
  clock: ['C12 12 10', 'M12 6v6l4 2'],
  check: ['C12 12 10', 'm9 12 2 2 4-4'],
  ban: ['C12 12 10', 'm4.9 4.9 14.2 14.2'],
  alert: ['m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3', 'M12 9v4', 'M12 17h.01'],
  info: ['C12 12 10', 'M12 16v-4', 'M12 8h.01'],
  rotate: ['M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.7 2.7L3 8', 'M3 3v5h5'],
  lock: ['M5 11h14v10H5z', 'M8 11V7a4 4 0 0 1 8 0v4'],
  loader: ['M21 12a9 9 0 1 1-6.2-8.6'],
  sun: ['C12 12 4', 'M12 2v2', 'M12 20v2', 'm4.9 4.9 1.4 1.4', 'm17.7 17.7 1.4 1.4', 'M2 12h2', 'M20 12h2', 'm6.3 17.7-1.4 1.4', 'm19.1 4.9-1.4 1.4'],
  cloud: ['M17.5 19H9a7 7 0 1 1 6.7-9h1.8a4.5 4.5 0 1 1 0 9z'],
  rain: ['M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2', 'M16 14v6', 'M8 14v6', 'M12 16v6'],
  fog: ['M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2', 'M16 17H7', 'M17 21H9'],
  thermometer: ['M14 4v10.5a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0z'],
} as const

export type IconName = keyof typeof PATHS

export function Icon({ name, small = false }: { name: IconName; small?: boolean }) {
  return (
    <svg
      className={small ? 'icon sm' : 'icon'}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.85}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name].map((d, i) => {
        if (d.startsWith('C')) {
          const [cx, cy, r] = d.slice(1).trim().split(' ')
          return <circle key={i} cx={cx} cy={cy} r={r} />
        }
        return <path key={i} d={d} />
      })}
    </svg>
  )
}
