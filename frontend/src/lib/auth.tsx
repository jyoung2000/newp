import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { api, ApiError, setCsrfToken, setUnauthorizedHandler } from './api'
import type { CsrfResponse, LoginResponse, UserOut } from './types'

type AuthStatus = 'loading' | 'authed' | 'anon'

interface AuthContextValue {
  status: AuthStatus
  user: UserOut | null
  login: (email: string, password: string) => Promise<{ requiresTotp: boolean }>
  verifyTotp: (code: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<UserOut | null>(null)
  const bootstrapped = useRef(false)

  const applyAuthed = useCallback((u: UserOut, csrf: string | null) => {
    setUser(u)
    setCsrfToken(csrf)
    setStatus('authed')
  }, [])

  const clearAuth = useCallback(() => {
    setUser(null)
    setCsrfToken(null)
    setStatus('anon')
  }, [])

  // On first load, if a session cookie exists /auth/me succeeds; then pull a
  // fresh CSRF token into memory. Any 401 means we start at the login screen.
  useEffect(() => {
    if (bootstrapped.current) return
    bootstrapped.current = true
    let cancelled = false
    ;(async () => {
      try {
        const me = await api.get<UserOut>('/api/auth/me')
        const csrf = await api.get<CsrfResponse>('/api/auth/csrf')
        if (!cancelled) applyAuthed(me, csrf.csrf_token)
      } catch {
        if (!cancelled) clearAuth()
      }
    })()
    return () => {
      cancelled = true
    }
  }, [applyAuthed, clearAuth])

  // Global 401 handler: bounce back to anon (ProtectedLayout redirects).
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setCsrfToken(null)
      setUser(null)
      setStatus('anon')
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  const login = useCallback(
    async (email: string, password: string): Promise<{ requiresTotp: boolean }> => {
      const res = await api.post<LoginResponse>('/api/auth/login', { email, password })
      if (res.requires_totp) {
        return { requiresTotp: true }
      }
      if (res.user) applyAuthed(res.user, res.csrf_token ?? null)
      return { requiresTotp: false }
    },
    [applyAuthed],
  )

  const verifyTotp = useCallback(
    async (code: string): Promise<void> => {
      const res = await api.post<LoginResponse>('/api/auth/totp', { code })
      if (!res.user) throw new ApiError(401, 'Verification failed')
      applyAuthed(res.user, res.csrf_token ?? null)
    },
    [applyAuthed],
  )

  const logout = useCallback(async (): Promise<void> => {
    try {
      await api.post('/api/auth/logout')
    } catch {
      /* ignore network/permission errors on logout */
    }
    clearAuth()
  }, [clearAuth])

  const refreshUser = useCallback(async (): Promise<void> => {
    try {
      const me = await api.get<UserOut>('/api/auth/me')
      setUser(me)
    } catch {
      /* ignore */
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, verifyTotp, logout, refreshUser }),
    [status, user, login, verifyTotp, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
