import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { apiFetch, refreshSession, type AuthPayload } from '../../lib/api'
import { clearTokens, setAccessToken, setRefreshToken } from '../../lib/auth-storage'

export interface SessionUser {
  id: number
  email: string
}

type Status = 'loading' | 'authenticated' | 'anonymous'

interface AuthValue {
  user: SessionUser | null
  status: Status
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  signOut: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null)
  const [status, setStatus] = useState<Status>('loading')

  // The access token lives in memory, so a reload starts signed out until the
  // stored refresh token proves otherwise.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      const restored = await refreshSession()
      if (cancelled) return
      if (!restored) {
        setStatus('anonymous')
        return
      }
      try {
        const me = await apiFetch<SessionUser>('/auth/me')
        if (cancelled) return
        setUser(me)
        setStatus('authenticated')
      } catch {
        if (!cancelled) setStatus('anonymous')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const adopt = useCallback((payload: AuthPayload) => {
    setAccessToken(payload.access_token)
    setRefreshToken(payload.refresh_token)
    setUser(payload.user)
    setStatus('authenticated')
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      adopt(
        await apiFetch<AuthPayload>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        }),
      )
    },
    [adopt],
  )

  const register = useCallback(
    async (email: string, password: string) => {
      adopt(
        await apiFetch<AuthPayload>('/auth/register', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        }),
      )
    },
    [adopt],
  )

  const signOut = useCallback(() => {
    clearTokens()
    setUser(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo(
    () => ({ user, status, login, register, signOut }),
    [user, status, login, register, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
