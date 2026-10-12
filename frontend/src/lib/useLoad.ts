import { useCallback, useEffect, useState } from 'react'

type LoadState<T> = { data: T | undefined; failed: boolean; reload: () => void }

/** Load data on mount and when the dependencies change. Call reload after a change. */
export function useLoad<T>(load: () => Promise<{ data?: T }>, deps: unknown[]): LoadState<T> {
  const [data, setData] = useState<T>()
  const [failed, setFailed] = useState(false)
  const [version, setVersion] = useState(0)
  // The caller lists the dependencies of load, as with useCallback.
  // oxlint-disable-next-line react-hooks/exhaustive-deps, react/use-memo
  const run = useCallback(load, deps)

  useEffect(() => {
    let current = true
    run().then(
      (result) => {
        if (!current) return
        setData(result.data)
        setFailed(result.data === undefined)
      },
      () => current && setFailed(true),
    )
    return () => {
      current = false
    }
  }, [run, version])

  return { data, failed, reload: () => setVersion((v) => v + 1) }
}
