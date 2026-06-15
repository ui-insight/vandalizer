import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { getProjectInviteInfo, acceptProjectInvite } from '../api/projects'
import type { ProjectInviteInfo } from '../types/project'

type Status = 'loading' | 'accepting' | 'success' | 'error' | 'needsAuth'

const STATUS_MESSAGES: Record<string, string> = {
  revoked: 'This invite link has been revoked.',
  expired: 'This invite link has expired. Ask for a new one.',
  exhausted: 'This invite link has reached its use limit.',
}

export default function JoinProjectAccept() {
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const token = search?.token

  const [status, setStatus] = useState<Status>('loading')
  const [info, setInfo] = useState<ProjectInviteInfo | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const acceptStartedRef = useRef(false)

  // Fetch invite metadata (public)
  useEffect(() => {
    if (!token) {
      setStatus('error')
      setErrorMsg('No invite token provided.')
      return
    }
    let cancelled = false
    getProjectInviteInfo(token)
      .then(data => {
        if (cancelled) return
        if (data.status) {
          setStatus('error')
          setErrorMsg(STATUS_MESSAGES[data.status] ?? 'This invite is no longer valid.')
          return
        }
        setInfo(data)
        // Defer to the accept effect once we know auth state.
        setStatus(s => (s === 'loading' ? 'loading' : s))
      })
      .catch(err => {
        if (cancelled) return
        setStatus('error')
        setErrorMsg(err instanceof Error ? err.message : 'Invalid invite link.')
      })
    return () => { cancelled = true }
  }, [token])

  // Accept once authed + info is loaded
  useEffect(() => {
    if (acceptStartedRef.current) return
    if (authLoading || !info || !token || status === 'error') return
    if (!user) { setStatus('needsAuth'); return }
    acceptStartedRef.current = true
    setStatus('accepting')
    acceptProjectInvite(token)
      .then(project => {
        setStatus('success')
        setTimeout(() => {
          navigate({
            to: '/',
            search: {
              mode: 'chat', tab: undefined, workflow: undefined, extraction: undefined,
              automation: undefined, kb: undefined, project: project.uuid, workflow_share_token: undefined,
            },
          })
        }, 1200)
      })
      .catch(err => {
        setStatus('error')
        setErrorMsg(err instanceof Error ? err.message : 'Failed to join project.')
      })
  }, [authLoading, user, token, info, status, navigate])

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0a0a] p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-[#171717] p-8 text-center shadow-xl">
        {(status === 'loading' || status === 'accepting') && (
          <>
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-[#f1b300] border-t-transparent" />
            <p className="mt-4 text-gray-300">
              {status === 'accepting' ? `Joining ${info?.project_title}…` : 'Loading invite…'}
            </p>
          </>
        )}

        {status === 'needsAuth' && info && (
          <>
            <h1 className="text-xl font-bold text-white">
              Join <span className="text-[#f1b300]">{info.project_title}</span>
            </h1>
            <p className="mt-2 text-sm text-gray-400">
              {info.inviter_name ? `${info.inviter_name} invited you` : 'You were invited'} to view and chat with this project.
            </p>
            <p className="mt-4 text-sm text-gray-400">Sign in or create an account, then re-open this link to join.</p>
            <a
              href="/landing"
              className="mt-6 inline-block rounded-lg bg-[#f1b300] px-4 py-2 text-sm font-bold text-black hover:bg-[#d49e00]"
            >
              Sign in
            </a>
          </>
        )}

        {status === 'success' && info && (
          <>
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-500/20 text-green-400">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="mt-4 text-lg font-semibold text-white">You've joined {info.project_title}!</h2>
            <p className="mt-2 text-sm text-gray-400">Opening the project…</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-500/20 text-red-400">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="mt-4 text-lg font-semibold text-white">Can't join</h2>
            <p className="mt-2 text-sm text-gray-400">{errorMsg}</p>
          </>
        )}
      </div>
    </div>
  )
}
