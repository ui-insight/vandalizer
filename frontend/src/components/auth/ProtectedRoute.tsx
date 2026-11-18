import { useEffect } from 'react'
import { Navigate } from '@tanstack/react-router'
import { useAuth } from '../../hooks/useAuth'
import {
  consumePendingInviteToken,
  consumePendingJoinLinkToken,
} from '../../lib/pendingInvite'
import { consumePendingNext } from '../../lib/pendingNext'

// Read once per page load, not per render: consuming removes it, and a second
// render (StrictMode, or auth state settling) must still see the answer.
let resumeTarget: string | null | undefined
function pendingNextOnce(): string | null {
  if (resumeTarget === undefined) resumeTarget = consumePendingNext()
  return resumeTarget
}

/** Test seam: forget the per-load answer. */
export function resetPendingNextForTests() {
  resumeTarget = undefined
}

function Spinner() {
  return (
    <div className="flex h-screen items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-highlight border-t-transparent" />
    </div>
  )
}

function ResumeLink({ to }: { to: string }) {
  useEffect(() => { window.location.replace(to) }, [to])
  return <Spinner />
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, demoExpired, demoFeedbackToken } = useAuth()

  if (loading) {
    return <Spinner />
  }

  // Expired trial → the renewal screen (warm thank-you + keep-going / feedback
  // for more time). Checked before the !user redirect so a mid-session expiry,
  // which clears the user, still lands here rather than on a bare landing page.
  if (demoExpired && demoFeedbackToken) {
    return <Navigate to="/demo/trial-end" search={{ token: demoFeedbackToken }} />
  }

  if (!user) {
    const here = window.location.pathname + window.location.search
    const next = here && here !== '/' && !here.startsWith('/landing') ? here : undefined
    return (
      <Navigate
        to="/landing"
        search={{ error: undefined, invite_token: undefined, admin: undefined, next, register: undefined }}
      />
    )
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

  // Single sign-on returns to "/" and drops the link the person opened before
  // signing in (for example a knowledge base's chat link). The sign-in page
  // parked it; go there now.
  const resume = pendingNextOnce()
  if (resume && resume !== window.location.pathname + window.location.search) {
    return <ResumeLink to={resume} />
  }

  return <>{children}</>
}
