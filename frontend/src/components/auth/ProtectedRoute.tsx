import { Navigate } from '@tanstack/react-router'
import { useAuth } from '../../hooks/useAuth'
import { consumePendingInviteToken } from '../../lib/pendingInvite'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, demoExpired, demoFeedbackToken } = useAuth()

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-highlight border-t-transparent" />
      </div>
    )
  }

  if (!user) return <Navigate to="/landing" search={{ error: undefined, invite_token: undefined, admin: undefined }} />

  if (demoExpired && demoFeedbackToken) {
    return <Navigate to="/demo/feedback" search={{ token: demoFeedbackToken }} />
  }

  // Resume invite flow if the user just completed OAuth/SAML from /invite —
  // those callbacks land on `/` and lose the token from the URL.
  const pendingInvite = consumePendingInviteToken()
  if (pendingInvite) {
    return <Navigate to="/invite" search={{ token: pendingInvite }} />
  }

  return <>{children}</>
}
