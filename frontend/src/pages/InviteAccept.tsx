import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { useTeams } from '../hooks/useTeams'
import { acceptInvite, getInviteInfo, type InviteInfo } from '../api/teams'

type Status = 'loading' | 'ready' | 'accepting' | 'success' | 'error'

export default function InviteAccept() {
  const { user, loading: authLoading, login, register } = useAuth()
  const { refreshTeams } = useTeams()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const token = search?.token

  const [status, setStatus] = useState<Status>('loading')
  const [info, setInfo] = useState<InviteInfo | null>(null)
  const [errorMsg, setErrorMsg] = useState('')

  // Fetch invite metadata (public — works authed or not)
  useEffect(() => {
    if (!token) {
      setStatus('error')
      setErrorMsg('No invite token provided.')
      return
    }
    let cancelled = false
    getInviteInfo(token)
      .then((data) => {
        if (cancelled) return
        if (data.expired) {
          setStatus('error')
          setErrorMsg('This invite has expired. Ask the team to send a new one.')
          return
        }
        setInfo(data)
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setStatus('error')
        setErrorMsg(err instanceof Error ? err.message : 'Invalid invite link.')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  // If already authenticated, accept immediately
  useEffect(() => {
    if (authLoading || status !== 'ready' || !user || !token) return
    let cancelled = false
    setStatus('accepting')
    acceptInvite(token)
      .then(async (result) => {
        if (cancelled) return
        await refreshTeams()
        setInfo((prev) => (prev ? { ...prev, team_name: result.name } : prev))
        setStatus('success')
        setTimeout(() => {
          if (cancelled) return
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
        }, 1500)
      })
      .catch((err) => {
        if (cancelled) return
        setStatus('error')
        setErrorMsg(
          err instanceof Error ? err.message : 'Failed to accept invite.',
        )
      })
    return () => {
      cancelled = true
    }
  }, [authLoading, user, token, status]) // eslint-disable-line react-hooks/exhaustive-deps

  if (status === 'loading' || authLoading) {
    return <CenteredCard><Spinner /><p className="mt-4 text-gray-300">Loading invite...</p></CenteredCard>
  }

  if (status === 'error') {
    return (
      <CenteredCard>
        <ErrorIcon />
        <h2 className="mt-4 text-lg font-semibold text-white">Invite unavailable</h2>
        <p className="mt-2 text-sm text-gray-400">{errorMsg}</p>
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
          className="mt-6 rounded-lg bg-[#f1b300] px-4 py-2 text-sm font-bold text-black hover:bg-[#d49e00]"
        >
          Continue
        </button>
      </CenteredCard>
    )
  }

  if (status === 'accepting') {
    return <CenteredCard><Spinner /><p className="mt-4 text-gray-300">Adding you to {info?.team_name}...</p></CenteredCard>
  }

  if (status === 'success' && info) {
    return (
      <CenteredCard>
        <SuccessIcon />
        <h2 className="mt-4 text-lg font-semibold text-white">
          You've joined {info.team_name}!
        </h2>
        <p className="mt-2 text-sm text-gray-400">Redirecting to your workspace...</p>
      </CenteredCard>
    )
  }

  // status === 'ready' and !user — show the invite landing with login/register
  if (!info || !token) return null

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0a0a] p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-[#171717] p-8 shadow-xl">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#f1b300]/10 text-[#f1b300]">
            <svg className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87M16 3.13a4 4 0 010 7.75M8 11a4 4 0 100-8 4 4 0 000 8z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">
            You're invited to <span className="text-[#f1b300]">{info.team_name}</span>
          </h1>
          {info.inviter_name && (
            <p className="mt-2 text-sm text-gray-400">
              {info.inviter_name} invited you to join as {info.role === 'member' ? 'a member' : `an ${info.role}`}.
            </p>
          )}
          <p className="mt-1 text-xs text-gray-500">Invite for {info.email}</p>
        </div>

        <div className="mt-8">
          <InviteAuthTabs
            info={info}
            token={token}
            onLogin={login}
            onRegister={register}
          />
        </div>
      </div>
    </div>
  )
}

function InviteAuthTabs({
  info,
  token,
  onLogin,
  onRegister,
}: {
  info: InviteInfo
  token: string
  onLogin: (userId: string, password: string) => Promise<void>
  onRegister: (
    userId: string,
    email: string,
    password: string,
    name?: string,
    inviteToken?: string,
  ) => Promise<void>
}) {
  const [mode, setMode] = useState<'register' | 'login'>('register')
  return (
    <>
      <div className="mb-4 flex rounded-lg bg-white/5 p-1">
        <button
          onClick={() => setMode('register')}
          className={`flex-1 rounded-md px-3 py-2 text-sm font-semibold transition-colors ${
            mode === 'register' ? 'bg-[#f1b300] text-black' : 'text-gray-400 hover:text-white'
          }`}
        >
          Create account
        </button>
        <button
          onClick={() => setMode('login')}
          className={`flex-1 rounded-md px-3 py-2 text-sm font-semibold transition-colors ${
            mode === 'login' ? 'bg-[#f1b300] text-black' : 'text-gray-400 hover:text-white'
          }`}
        >
          Sign in
        </button>
      </div>
      {mode === 'register' ? (
        <InviteRegisterForm info={info} token={token} onRegister={onRegister} />
      ) : (
        <InviteLoginForm info={info} onLogin={onLogin} />
      )}
    </>
  )
}

function InviteRegisterForm({
  info,
  token,
  onRegister,
}: {
  info: InviteInfo
  token: string
  onRegister: (
    userId: string,
    email: string,
    password: string,
    name?: string,
    inviteToken?: string,
  ) => Promise<void>
}) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await onRegister(info.email, info.email, password, name || undefined, token)
      // Auth context now has the user; parent effect will accept & redirect.
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && (
        <div className="rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
          {error}
        </div>
      )}
      <input
        type="email"
        value={info.email}
        readOnly
        aria-label="Email"
        className="w-full cursor-not-allowed rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-gray-400"
      />
      <input
        type="text"
        placeholder="Full name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
      />
      <input
        type="password"
        placeholder="Create a password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
      />
      <p className="text-xs text-gray-500">
        8+ characters with uppercase, lowercase, and a digit.
      </p>
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-lg bg-[#f1b300] px-4 py-3 font-bold text-black transition-all hover:bg-[#d49e00] disabled:opacity-50"
      >
        {submitting ? 'Creating account...' : `Join ${info.team_name}`}
      </button>
    </form>
  )
}

function InviteLoginForm({
  info,
  onLogin,
}: {
  info: InviteInfo
  onLogin: (userId: string, password: string) => Promise<void>
}) {
  const [userId, setUserId] = useState(info.email)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await onLogin(userId, password)
      // Auth context now has the user; parent effect will accept & redirect.
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && (
        <div className="rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
          {error}
        </div>
      )}
      <input
        type="text"
        placeholder="Email"
        required
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
      />
      <input
        type="password"
        placeholder="Password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
      />
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-lg bg-[#f1b300] px-4 py-3 font-bold text-black transition-all hover:bg-[#d49e00] disabled:opacity-50"
      >
        {submitting ? 'Signing in...' : 'Sign in & join'}
      </button>
    </form>
  )
}

function CenteredCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0a0a] p-4">
      <div className="w-full max-w-md rounded-xl border border-white/10 bg-[#171717] p-8 text-center shadow-xl">
        {children}
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-[#f1b300] border-t-transparent" />
  )
}

function SuccessIcon() {
  return (
    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-500/20 text-green-400">
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
      </svg>
    </div>
  )
}

function ErrorIcon() {
  return (
    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-500/20 text-red-400">
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </div>
  )
}
