import { Navigate } from '@tanstack/react-router'
import { useAuth } from '../../hooks/useAuth'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, demoExpired, demoFeedbackToken } = useAuth()

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-highlight border-t-transparent" />
      </div>
    )
  }

  if (!user) return <Navigate to="/landing" search={{ error: undefined, invite_token: undefined }} />

  if (demoExpired && demoFeedbackToken) {
    return <Navigate to="/demo/feedback" search={{ token: demoFeedbackToken }} />
  }

  return <>{children}</>
}
