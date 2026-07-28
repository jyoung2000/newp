import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

export type ThemePref = 'light' | 'dark' | 'system'

interface ThemeContextValue {
  pref: ThemePref
  resolved: 'light' | 'dark'
  setPref: (p: ThemePref) => void
  toggle: () => void
}

const STORAGE_KEY = 'jobpilot.theme'
const ThemeContext = createContext<ThemeContextValue | null>(null)

function systemDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch {
    /* ignore */
  }
  return 'system'
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>(readPref)
  const [systemIsDark, setSystemIsDark] = useState<boolean>(systemDark)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemIsDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const resolved: 'light' | 'dark' = pref === 'system' ? (systemIsDark ? 'dark' : 'light') : pref

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', resolved === 'dark')
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', resolved === 'dark' ? '#0b0d12' : '#f5f5f5')
  }, [resolved])

  const setPref = useCallback((p: ThemePref) => {
    setPrefState(p)
    try {
      localStorage.setItem(STORAGE_KEY, p)
    } catch {
      /* ignore */
    }
  }, [])

  const toggle = useCallback(() => {
    setPref(resolved === 'dark' ? 'light' : 'dark')
  }, [resolved, setPref])

  const value = useMemo<ThemeContextValue>(
    () => ({ pref, resolved, setPref, toggle }),
    [pref, resolved, setPref, toggle],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
