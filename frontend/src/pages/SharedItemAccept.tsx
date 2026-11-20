import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { redeemSearchSetShareToken } from '../api/extractions'

type Status = 'loading' | 'needsAuth' | 'error'

/**
 * Where a Skill or extraction share link lands. Records the signed-in person
 * as someone the item is shared with, then opens it: a Skill in a new chat,
 * an extraction in the Library. They can use and copy it, not edit it.
 */
export default function SharedItemAccept() {
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const item = search?.item
  const token = search?.token

  const [status, setStatus] = useState<Status>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current || authLoading) return
    if (!item || !token) {
      setStatus('error')
      setErrorMsg('This share link is incomplete. Ask for a new one.')
      return
    }
    if (!user) { setStatus('needsAuth'); return }
    startedRef.current = true
    redeemSearchSetShareToken(item, token)
      .then(shared => {
        const base = {
          mode: undefined, tab: undefined, workflow: undefined, extraction: undefined,
          automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined,
        }
        navigate({
          to: '/',
          replace: true,
          search: shared.set_type === 'prompt'
            ? { ...base, mode: 'chat' as const, skill: shared.uuid }
            : { ...base, tab: 'library' as const, extraction: shared.uuid },
        })
      })
      .catch(err => {
        setStatus('error')
        setErrorMsg(err instanceof Error && err.message ? err.message : 'This share link is not valid. Ask for a new one.')
      })
  }, [authLoading, user, item, token, navigate])

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0a0a] p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-[#171717] p-8 text-center shadow-xl">
        {status === 'loading' && (
          <>
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-highlight-on-dark border-t-transparent" />
            <p className="mt-4 text-gray-300" role="status">Opening the shared item…</p>
          </>
        )}

        {status === 'needsAuth' && (
          <>
            <h1 className="text-xl font-bold text-white">Someone shared an item with you</h1>
            <p className="mt-4 text-sm text-gray-400">Sign in or create an account, then re-open this link.</p>
            <a
              href="/landing"
              className="mt-6 inline-block rounded-lg bg-highlight px-4 py-2 text-sm font-bold text-highlight-text hover:bg-highlight-hover"
            >
              Sign in
            </a>
          </>
        )}

        {status === 'error' && (
          <>
            <h1 className="text-lg font-semibold text-white">Can't open this link</h1>
            <p className="mt-2 text-sm text-gray-400" role="alert">{errorMsg}</p>
            <a href="/" className="mt-6 inline-block text-sm font-medium text-highlight-on-dark underline">Go to Vandalizer</a>
          </>
        )}
      </div>
    </div>
  )
}
