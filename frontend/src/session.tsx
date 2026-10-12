import { createContext, useContext } from 'react'
import type { Me } from './api/client'

export const SessionContext = createContext<Me | null>(null)

/** The signed-in user. Use it only inside the signed-in part of the app. */
export function useMe(): Me {
  const me = useContext(SessionContext)
  if (!me) throw new Error('useMe needs a signed-in user')
  return me
}
