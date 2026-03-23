import { useEffect, useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { useTeams } from '../hooks/useTeams'
import { acceptInvite } from '../api/teams'

type Status = 'loading' | 'success' | 'error' | 'redirecting'

export default function InviteAccept() {
  const { user, loading: authLoading } = useAuth()
  const { refreshTeams } = useTeams()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const token = search?.token

  const [status, setStatus] = useState<Status>('loading')
  const [teamName, setTeamName] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => {
    if (authLoading) return

    if (!token) {
      setStatus('error')
      setErrorMsg('No invite token provided.')
      return
    }

    // Not authenticated — redirect to landing with invite_token preserved
    if (!user) {
      setStatus('redirecting')
      window.location.href = `/landing?invite_token=${encodeURIComponent(token)}`
      return
    }

    // Authenticated — accept the invite
    let cancelled = false
    setStatus('loading')

    acceptInvite(token)
      .then(async (result) => {
        if (cancelled) return
        setTeamName(result.name)
        setStatus('success')
        await refreshTeams()
        setTimeout(() => {
          if (!cancelled) {
            navigate({
              to: '/',
              search: {
                mode: undefined,
                tab: undefined,
                workflow: undefined,
                extraction: undefined,
                automation: undefined,
                kb: undefined,
              },
            })
          }
        }, 2000)
      })
      .catch((err) => {
        if (cancelled) return
        setStatus('error')
        setErrorMsg(
          err instanceof Error ? err.message : 'Invalid or expired invite link.',
        )
      })

    return () => {
      cancelled = true
    }
  }, [authLoading, user, token]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 shadow-sm text-center">
        {(status === 'loading' || status === 'redirecting') && (
          <>
            <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
            <p className="text-gray-600">
              {status === 'redirecting'
                ? 'Redirecting to sign in...'
                : 'Accepting invite...'}
            </p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-green-600">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-gray-900">
              You've joined {teamName}!
            </h2>
            <p className="mt-2 text-sm text-gray-500">
              Redirecting to your workspace...
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-600">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-gray-900">
              Invite Failed
            </h2>
            <p className="mt-2 text-sm text-gray-500">{errorMsg}</p>
            <button
              onClick={() =>
                navigate({
                  to: '/',
                  search: {
                    mode: undefined,
                    tab: undefined,
                    workflow: undefined,
                    extraction: undefined,
                    automation: undefined,
                    kb: undefined,
                  },
                })
              }
              className="mt-4 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
            >
              Go to Workspace
            </button>
          </>
        )}
      </div>
    </div>
  )
}
