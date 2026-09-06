import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuth } from '../features/auth/AuthContext'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth()

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-small text-text-secondary">Checking your session…</p>
      </div>
    )
  }
  if (status === 'anonymous') return <Navigate to="/login" replace />
  return <>{children}</>
}
