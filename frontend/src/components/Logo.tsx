/** The cup mark: a winged piston on a connecting rod. One shape set for every version. */
function CupShapes() {
  return (
    <>
      <path d="M21 8h22a2 2 0 0 1 2 2v3H19v-3a2 2 0 0 1 2-2z" />
      <rect x="19" y="14.5" width="26" height="2.5" />
      <path d="M19 18.5h26V26a2 2 0 0 1-2 2H21a2 2 0 0 1-2-2z" />
      <path d="M17.5 10H6.5L4 14h13.5zM17.5 16H9l-2.5 4h11zM17.5 22h-6l-2.5 4h8.5z" />
      <path d="M46.5 10h11L60 14H46.5zM46.5 16H55l2.5 4h-11zM46.5 22h6l2.5 4h-8.5z" />
      <path d="M28.5 28h7l-1.5 13h-4z" />
      <path d="M23 48v-5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v5h-4a5 5 0 0 0-10 0z" />
      <path d="M20 56l2.5-6.5h19L44 56z" />
      <rect x="17" y="56.5" width="30" height="3.5" rx="1" />
    </>
  )
}

/** The mark. `tile` draws the white cup on the red tile; `mono` draws the cup in the text colour. */
export function LogoMark({ size = 34, variant = 'tile' }: { size?: number; variant?: 'tile' | 'mono' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      {variant === 'tile' && <rect width="64" height="64" rx="12" fill="var(--brand)" />}
      <g fill={variant === 'tile' ? 'var(--on-brand)' : 'currentColor'}>
        <CupShapes />
      </g>
    </svg>
  )
}

/** The mark with the live-text wordmark. */
export function Logo({ size = 34 }: { size?: number }) {
  return (
    <>
      <LogoMark size={size} />
      <span className="wordmark">
        <b>PISTON CUP</b>
        <span>PADDOCK</span>
      </span>
    </>
  )
}
