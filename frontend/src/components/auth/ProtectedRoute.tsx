import { Navigate } from '@tanstack/react-router'
import { useAuth } from '../../hooks/useAuth'
import {
  consumePendingInviteToken,
  consumePendingJoinLinkToken,
} from '../../lib/pendingInvite'
import { useAppMode } from '../../contexts/AppModeContext'

const RA_ALLOWED_PREFIXES = ['/', '/chat', '/workflows']
const isAllowedForRA = (path: string) =>
  path === '/' || RA_ALLOWED_PREFIXES.slice(1).some(p => path.startsWith(p))

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, demoExpired, demoFeedbackToken } = useAuth()
  const { isRA } = useAppMode()

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-highlight border-t-transparent" />
      </div>
    )
  }

  if (!user) {
    const here = window.location.pathname + window.location.search
    const next = here && here !== '/' && !here.startsWith('/landing') ? here : undefined
    return (
      <Navigate
        to="/landing"
        search={{ error: undefined, invite_token: undefined, admin: undefined, next }}
      />
    )
  }

  if (demoExpired && demoFeedbackToken) {
    return <Navigate to="/demo/feedback" search={{ token: demoFeedbackToken }} />
  }

  // Resume invite/join flow if the user just completed OAuth/SAML from
  // /invite or /join — those callbacks land on `/` and lose the token.
  const pendingInvite = consumePendingInviteToken()
  if (pendingInvite) {
    return <Navigate to="/invite" search={{ token: pendingInvite }} />
  }
  const pendingJoin = consumePendingJoinLinkToken()
  if (pendingJoin) {
    return <Navigate to="/join" search={{ token: pendingJoin }} />
  }

  if (isRA && !isAllowedForRA(window.location.pathname)) {
    return <Navigate to="/" search={{ mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, workflow_share_token: undefined }} />
  }

  return <>{children}</>
}
