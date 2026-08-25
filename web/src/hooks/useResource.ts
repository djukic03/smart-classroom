import { useCallback, useEffect, useRef, useState } from 'react'

export interface Resource<T> {
  data: T | null
  error: Error | null
  loading: boolean
  refreshing: boolean
  refresh: () => void
}

interface State<T> {
  data: T | null
  error: Error | null
  loading: boolean
  refreshing: boolean
}


export function useResource<T>(
  key: string,
  fetcher: () => Promise<T>,
  intervalMs = 0,
): Resource<T> {
  const [state, setState] = useState<State<T>>({
    data: null,
    error: null,
    loading: true,
    refreshing: false,
  })

  const fetcherRef = useRef(fetcher)
  useEffect(() => {
    fetcherRef.current = fetcher
  })

  const generation = useRef(0)

  const run = useCallback(async (quiet: boolean) => {
    const mine = ++generation.current
    setState((s) => (quiet ? { ...s, refreshing: true } : { ...s, loading: true }))

    try {
      const data = await fetcherRef.current()
      if (mine !== generation.current) return
      setState({ data, error: null, loading: false, refreshing: false })
    } catch (error) {
      if (mine !== generation.current) return
      setState((s) => ({
        ...s,
        error: error as Error,
        loading: false,
        refreshing: false,
      }))
    }
  }, [])

  useEffect(() => {
    setState({ data: null, error: null, loading: true, refreshing: false })
    void run(false)
  }, [key, run])

  useEffect(() => {
    if (intervalMs <= 0) return

    const tick = () => {
      if (!document.hidden) void run(true)
    }
    const id = window.setInterval(tick, intervalMs)
    document.addEventListener('visibilitychange', tick)

    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [key, intervalMs, run])

  const refresh = useCallback(() => void run(true), [run])

  return { ...state, refresh }
}
