import { createContext, useContext } from 'react'
import type { Me } from './api/client'

export type Mode = 'driver' | 'admin'

export type Session = { me: Me; mode: Mode; setMode: (mode: Mode) => void }

export const SessionContext = createContext<Session | null>(null)
export const MODE_KEY = 'paddock.mode'

function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('useSession needs a signed-in user')
  return session
}

/** The signed-in user. Use it only inside the signed-in part of the app. */
export function useMe(): Me {
  return useSession().me
}

export function useMode(): { mode: Mode; setMode: (mode: Mode) => void } {
  const { mode, setMode } = useSession()
  return { mode, setMode }
}

/** True when the page must show its admin forms: the user can manage, and the admin mode is on. */
export function useAdminView(canManage: boolean): boolean {
  const { me, mode } = useSession()
  return canManage && me.can_admin && mode === 'admin'
}
