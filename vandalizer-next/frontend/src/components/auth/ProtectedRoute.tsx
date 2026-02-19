import { Navigate } from '@tanstack/react-router'
import { useAuth } from '../../hooks/useAuth'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-highlight border-t-transparent" />
      </div>
    )
  }

  if (!user) return <Navigate to="/login" />

  return <>{children}</>
}
