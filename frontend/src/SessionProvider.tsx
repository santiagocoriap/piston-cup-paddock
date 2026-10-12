import { useCallback, useState, type ReactNode } from 'react'
import type { Me } from './api/client'
import { MODE_KEY, SessionContext, type Mode } from './session'

function readMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === 'admin' ? 'admin' : 'driver'
  } catch {
    return 'driver'
  }
}

/** Gives the signed-in user and the mode. The app starts in the driver mode. */
export function SessionProvider({ me, children }: { me: Me; children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(() => (me.can_admin ? readMode() : 'driver'))
  const setMode = useCallback((next: Mode) => {
    setModeState(next)
    try {
      localStorage.setItem(MODE_KEY, next)
    } catch {
      // The browser blocks storage. The mode then lasts only for this page.
    }
  }, [])
  return <SessionContext.Provider value={{ me, mode, setMode }}>{children}</SessionContext.Provider>
}

