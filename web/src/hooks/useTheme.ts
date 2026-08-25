import { useCallback, useEffect, useMemo, useState } from 'react'

import { readStored, writeStored } from '@/lib/storage'

export type ThemeChoice = 'system' | 'light' | 'dark'

const KEY = 'sc.theme'

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}


export function useTheme(): { dark: boolean; toggle: () => void } {
  const [choice, setChoice] = useState<ThemeChoice>(() =>
    readStored<ThemeChoice>(KEY, 'system'),
  )
  const [system, setSystem] = useState(() =>
    typeof window === 'undefined' ? false : systemPrefersDark(),
  )

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e: MediaQueryListEvent) => setSystem(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    if (choice === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', choice)
    writeStored(KEY, choice)
  }, [choice])

  const dark = choice === 'system' ? system : choice === 'dark'

  const toggle = useCallback(() => {
    setChoice(dark ? 'light' : 'dark')
  }, [dark])

  return useMemo(() => ({ dark, toggle }), [dark, toggle])
}
