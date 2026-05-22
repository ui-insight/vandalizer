import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { useTeams } from '../hooks/useTeams'
import { acceptJoinLink, getJoinLinkInfo, type JoinLinkInfo } from '../api/teams'
import { getAuthConfig, type AuthConfig } from '../api/auth'
import { PENDING_JOIN_LINK_TOKEN_KEY } from '../lib/pendingInvite'

type Status = 'loading' | 'ready' | 'accepting' | 'success' | 'error'

const STATUS_MESSAGES: Record<NonNullable<JoinLinkInfo['status']>, string> = {
  revoked: 'This join link has been revoked by the team.',
  expired: 'This join link has expired. Ask the team for a new one.',
  exhausted: 'This join link has reached its use limit.',
}

export default function JoinLinkAccept() {
  const { user, loading: authLoading, login, register } = useAuth()
  const { refreshTeams } = useTeams()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const token = search?.token

  const [status, setStatus] = useState<Status>('loading')
  const [info, setInfo] = useState<JoinLinkInfo | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)
  const acceptStartedRef = useRef(false)

  // Clear any stashed token now that we've reached the join page.
  useEffect(() => {
    sessionStorage.removeItem(PENDING_JOIN_LINK_TOKEN_KEY)
  }, [])

  useEffect(() => {
    getAuthConfig().then(setAuthConfig).catch(() => setAuthConfig(null))
  }, [])

  // Fetch join-link metadata (public — works authed or not)
  useEffect(() => {
    if (!token) {
      setStatus('error')
      setErrorMsg('No join token provided.')
      return
    }
    let cancelled = false
    getJoinLinkInfo(token)
      .then((data) => {
        if (cancelled) return
        if (data.status) {
          setStatus('error')
          setErrorMsg(STATUS_MESSAGES[data.status])
          return
        }
        setInfo(data)
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setStatus('error')
        setErrorMsg(err instanceof Error ? err.message : 'Invalid join link.')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    if (acceptStartedRef.current) return
    if (authLoading || status !== 'ready' || !user || !token) return
    acceptStartedRef.current = true
    setStatus('accepting')
    acceptJoinLink(token)
      .then(async (result) => {
        await refreshTeams()
        setInfo((prev) => (prev ? { ...prev, team_name: result.name } : prev))
        setStatus('success')
        setTimeout(() => {
          navigate({
            to: '/',
            search: {
              mode: undefined,
              tab: undefined,
              workflow: undefined,
              extraction: undefined,
              automation: undefined,
              kb: undefined,
              workflow_share_token: undefined,
            },
          })
        }, 1500)
      })
      .catch((err) => {
        setStatus('error')
        setErrorMsg(err instanceof Error ? err.message : 'Failed to join team.')
      })
  }, [authLoading, user, token, status]) // eslint-disable-line react-hooks/exhaustive-deps

  if (status === 'loading' || authLoading) {
    return <CenteredCard><Spinner /><p className="mt-4 text-gray-300">Loading join link...</p></CenteredCard>
  }

  if (status === 'error') {
    return (
      <CenteredCard>
        <ErrorIcon />
        <h2 className="mt-4 text-lg font-semibold text-white">Can't join</h2>
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
                workflow_share_token: undefined,
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
    return <CenteredCard><Spinner /><p className="mt-4 text-gray-300">Joining {info?.team_name}...</p></CenteredCard>
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
            Join <span className="text-[#f1b300]">{info.team_name}</span>
          </h1>
          <p className="mt-2 text-sm text-gray-400">
            {info.inviter_name
              ? `${info.inviter_name} shared a link to join as ${info.role === 'member' ? 'a member' : `an ${info.role}`}.`
              : `You've been invited to join as ${info.role === 'member' ? 'a member' : `an ${info.role}`}.`}
          </p>
        </div>

        <div className="mt-8">
          <JoinAuthTabs
            info={info}
            token={token}
            authConfig={authConfig}
            onLogin={login}
            onRegister={register}
          />
        </div>
      </div>
    </div>
  )
}

function JoinAuthTabs({
  info,
  token,
  authConfig,
  onLogin,
  onRegister,
}: {
  info: JoinLinkInfo
  token: string
  authConfig: AuthConfig | null
  onLogin: (userId: string, password: string) => Promise<void>
  onRegister: (
    userId: string,
    email: string,
    password: string,
    name?: string,
    inviteToken?: string,
    joinLinkToken?: string,
  ) => Promise<void>
}) {
  const [mode, setMode] = useState<'register' | 'login'>('register')

  const oauthEnabled = authConfig?.auth_methods.includes('oauth') ?? false
  const passwordEnabled = authConfig?.auth_methods.includes('password') ?? true
  const azureProvider = authConfig?.oauth_providers.find(
    (p) => p.provider === 'azure' && p.configured,
  )
  const samlProvider = authConfig?.oauth_providers.find(
    (p) => p.provider === 'saml',
  )

  const stashTokenForOAuth = () => {
    sessionStorage.setItem(PENDING_JOIN_LINK_TOKEN_KEY, token)
  }

  return (
    <>
      {oauthEnabled && azureProvider && (
        <a
          href="/api/auth/oauth/azure"
          onClick={stashTokenForOAuth}
          className="mb-3 flex w-full items-center justify-center gap-2 rounded-lg bg-white px-4 py-3 font-bold text-black transition-all hover:bg-gray-200"
        >
          {azureProvider.display_name} & join {info.team_name}
        </a>
      )}

      {samlProvider && (
        <a
          href="/api/auth/saml/login"
          onClick={stashTokenForOAuth}
          className="mb-3 flex w-full items-center justify-center gap-2 rounded-lg bg-[#f1b300] px-4 py-3 font-bold text-black transition-all hover:bg-[#d49e00]"
        >
          {samlProvider.display_name || 'Sign in with University SSO'} & join
        </a>
      )}

      {((oauthEnabled && azureProvider) || samlProvider) && passwordEnabled && (
        <div className="relative my-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-white/10" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="bg-[#171717] px-4 text-gray-500">or</span>
          </div>
        </div>
      )}

      {passwordEnabled && (
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
            <JoinRegisterForm info={info} token={token} onRegister={onRegister} />
          ) : (
            <JoinLoginForm info={info} onLogin={onLogin} />
          )}
        </>
      )}
    </>
  )
}

function JoinRegisterForm({
  info,
  token,
  onRegister,
}: {
  info: JoinLinkInfo
  token: string
  onRegister: (
    userId: string,
    email: string,
    password: string,
    name?: string,
    inviteToken?: string,
    joinLinkToken?: string,
  ) => Promise<void>
}) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await onRegister(email, email, password, name || undefined, undefined, token)
      // Parent effect will detect the new user and call acceptJoinLink — but
      // the register endpoint also auto-accepts join_link_token, so we're
      // covered either way (idempotent: existing membership is a no-op).
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
        placeholder="Email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
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

function JoinLoginForm({
  info,
  onLogin,
}: {
  info: JoinLinkInfo
  onLogin: (userId: string, password: string) => Promise<void>
}) {
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await onLogin(userId, password)
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
        {submitting ? 'Signing in...' : `Sign in & join ${info.team_name}`}
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
