import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useSearch } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { getAuthConfig, type AuthConfig } from '../api/auth'
import { Footer } from '../components/layout/Footer'
import { useBranding } from '../contexts/BrandingContext'
import {
  ArrowDown,
  BadgeCheck,
  Bot,
  Check,
  CheckCircle,
  Database,
  FileInput,
  GitMerge,
  Lock,
  MessageSquare,
  PenTool,
  PlayCircle,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

function LandingLoginForm() {
  const { login } = useAuth()
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(userId, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 w-full max-w-sm mx-auto">
      {error && (
        <div
          role="alert"
          id="landing-login-error"
          className="rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200"
        >
          {error}
        </div>
      )}
      <label htmlFor="landing-login-email" className="sr-only">Email</label>
      <input
        id="landing-login-email"
        type="email"
        autoComplete="username"
        placeholder="Email"
        required
        aria-invalid={!!error}
        aria-describedby={error ? 'landing-login-error' : undefined}
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        className="landing-auth-input"
      />
      <label htmlFor="landing-login-password" className="sr-only">Password</label>
      <input
        id="landing-login-password"
        type="password"
        autoComplete="current-password"
        placeholder="Password"
        required
        aria-invalid={!!error}
        aria-describedby={error ? 'landing-login-error' : undefined}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="landing-auth-input"
      />
      <button type="submit" disabled={submitting} className="launch-brand-button w-full justify-center">
        {submitting ? 'Signing in…' : 'Sign in'}
      </button>
      <p className="text-center text-sm">
        <Link to="/reset-password" search={{ token: undefined }} className="text-zinc-400 transition-colors hover:text-white">
          Forgot password?
        </Link>
      </p>
    </form>
  )
}

function LandingRegisterForm({ onSwitch }: { onSwitch: () => void }) {
  const { register } = useAuth()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await register(email, email, password, name || undefined, undefined, undefined, role || undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 w-full max-w-sm mx-auto">
      {error && (
        <div
          role="alert"
          id="landing-register-error"
          className="rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200"
        >
          {error}
        </div>
      )}
      <label htmlFor="landing-register-name" className="sr-only">Full name</label>
      <input
        id="landing-register-name"
        type="text"
        autoComplete="name"
        placeholder="Full name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="landing-auth-input"
      />
      <label htmlFor="landing-register-email" className="sr-only">Email address</label>
      <input
        id="landing-register-email"
        type="email"
        autoComplete="email"
        placeholder="Email address"
        required
        aria-invalid={!!error}
        aria-describedby={error ? 'landing-register-error' : undefined}
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="landing-auth-input"
      />
      <label htmlFor="landing-register-password" className="sr-only">Password</label>
      <input
        id="landing-register-password"
        type="password"
        autoComplete="new-password"
        placeholder="Password"
        required
        aria-invalid={!!error}
        aria-describedby={error ? 'landing-register-error' : undefined}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="landing-auth-input"
      />
      <label htmlFor="landing-register-role" className="sr-only">Your role</label>
      <select
        id="landing-register-role"
        value={role}
        onChange={(e) => setRole(e.target.value)}
        className="landing-auth-input"
      >
        <option value="">Your role (optional)</option>
        <option value="research_admin">Research Administrator</option>
        <option value="pi">Principal Investigator</option>
        <option value="sponsored_programs">Sponsored Programs / OSP</option>
        <option value="compliance">Compliance</option>
        <option value="it">IT / Systems</option>
        <option value="other">Other</option>
      </select>
      <button type="submit" disabled={submitting} className="launch-brand-button w-full justify-center">
        {submitting ? 'Creating account…' : 'Create account'}
      </button>
      <p className="text-center text-sm text-zinc-400">
        Already have an account?{' '}
        <button type="button" onClick={onSwitch} className="font-semibold text-white transition-colors hover:text-highlight">
          Sign in
        </button>
      </p>
    </form>
  )
}

function AuthBlock({ config }: { config: AuthConfig | null }) {
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  // `/landing?register=1` opens in register mode. The trial CTA on /demo and
  // the /register redirect deep-link here; without it a would-be signup
  // landed on the login form and had to find the small "Create account" toggle.
  const [mode, setMode] = useState<'login' | 'register'>(
    search?.register === '1' ? 'register' : 'login',
  )
  const oauthError = search?.error
  const adminOverride = search?.admin === '1'

  if (!config) {
    return (
      <div className="flex justify-center py-8" aria-live="polite">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-highlight border-t-transparent" />
        <span className="sr-only">Loading sign-in options</span>
      </div>
    )
  }

  const oauthEnabled = config.auth_methods.includes('oauth')
  // The trial is password self-registration — POST /api/auth/register has no
  // auth-method gate — so a deployment that switched password sign-in off for
  // its own staff still needs this block whenever the trial system is on.
  // Otherwise "Create your account" on /demo lands on an empty landing page.
  const passwordEnabled =
    config.auth_methods.includes('password') || adminOverride || !!config.trial_system_enabled
  const azureProvider = config.oauth_providers.find(
    (p) => p.provider === 'azure' && p.configured,
  )
  const samlProvider = config.oauth_providers.find(
    (p) => p.provider === 'saml',
  )

  return (
    <div className="w-full max-w-sm mx-auto">
      {oauthError && (
        <div className="mb-4 rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">
          Authentication failed. Please try again.
        </div>
      )}

      {oauthEnabled && azureProvider && (
        <div className="mb-4">
          <a href="/api/auth/oauth/azure" className="launch-light-button w-full justify-center">
            {azureProvider.display_name}
          </a>
        </div>
      )}

      {samlProvider && (
        <div className="mb-4">
          <a href="/api/auth/saml/login" className="launch-brand-button w-full justify-center">
            {samlProvider.display_name || 'Sign in with University SSO'}
          </a>
        </div>
      )}

      {oauthEnabled && azureProvider && passwordEnabled && (
        <div className="landing-auth-divider"><span>or</span></div>
      )}

      {passwordEnabled && (
        <>
          {mode === 'login' ? (
            <>
              <LandingLoginForm />
              <p className="mt-4 text-center text-sm text-zinc-400">
                Don&apos;t have an account?{' '}
                <button onClick={() => setMode('register')} className="font-semibold text-white transition-colors hover:text-highlight">
                  Create account
                </button>
              </p>
            </>
          ) : (
            <LandingRegisterForm onSwitch={() => setMode('login')} />
          )}
        </>
      )}

      {!passwordEnabled && config.demo_login_enabled && (
        <p className="mt-6 text-center text-sm text-zinc-400">
          Have a trial account?{' '}
          <Link to="/login" className="font-semibold text-white transition-colors hover:text-highlight">
            Log in here
          </Link>
        </p>
      )}
    </div>
  )
}

function AccessDialog({ config, orgName, onClose }: { config: AuthConfig | null; orgName: string; onClose: () => void }) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="launch-access-overlay" role="presentation" onMouseDown={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="access-dialog-title"
        className="launch-access-dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button type="button" onClick={onClose} className="launch-dialog-close" aria-label="Close sign-in dialog">Close</button>
        <div className="mx-auto max-w-sm text-center">
          <p className="launch-eyebrow"><MessageSquare className="h-4 w-4" /> Welcome back</p>
          <h2 id="access-dialog-title" className="mt-5 text-3xl font-semibold tracking-[-0.045em] text-white">Continue with {orgName}.</h2>
          <p className="mt-3 text-sm leading-6 text-zinc-400">Sign in to your workspace or create an account to get started.</p>
        </div>
        <div className="mt-8"><AuthBlock config={config} /></div>
      </section>
    </div>
  )
}

function DemoRequestForm() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [institution, setInstitution] = useState('')
  const [role, setRole] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const res = await fetch('/api/demo/request-contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, institution, role, message }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Could not submit request')
      }
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit request')
    } finally {
      setSubmitting(false)
    }
  }

  if (success) {
    return (
      <div className="launch-demo-form text-center" role="status">
        <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-green-400/15 text-green-300">
          <Check className="h-6 w-6" />
        </div>
        <h3 className="text-2xl font-semibold text-white">Thanks, we&apos;ll be in touch soon.</h3>
        <p className="mt-2 text-zinc-400">Someone from the team will reach out within one business day to schedule your walkthrough.</p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="launch-demo-form space-y-4 text-left">
      {error && <div className="rounded-xl border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</div>}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="sr-only" htmlFor="demo-name">Your name</label>
        <input id="demo-name" type="text" required placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} className="landing-auth-input" />
        <label className="sr-only" htmlFor="demo-email">Work email</label>
        <input id="demo-email" type="email" required placeholder="Work email" value={email} onChange={(e) => setEmail(e.target.value)} className="landing-auth-input" />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="sr-only" htmlFor="demo-institution">Institution or organization</label>
        <input id="demo-institution" type="text" required placeholder="Institution / organization" value={institution} onChange={(e) => setInstitution(e.target.value)} className="landing-auth-input" />
        <label className="sr-only" htmlFor="demo-role">Your role</label>
        <select id="demo-role" required value={role} onChange={(e) => setRole(e.target.value)} className="landing-auth-input">
          <option value="" disabled>Your role</option>
          <option value="research_admin">Research Administrator</option>
          <option value="pi">Principal Investigator</option>
          <option value="sponsored_programs">Sponsored Programs / OSP</option>
          <option value="compliance">Compliance</option>
          <option value="it">IT / Systems</option>
          <option value="other">Other</option>
        </select>
      </div>
      <label className="sr-only" htmlFor="demo-message">What would you like to see?</label>
      <textarea id="demo-message" placeholder="What would you like to see in the demo? (optional)" value={message} onChange={(e) => setMessage(e.target.value)} rows={3} className="landing-auth-input resize-none" />
      <button type="submit" disabled={submitting} className="launch-light-button w-full justify-center text-base">
        <PlayCircle className="h-5 w-5" />
        {submitting ? 'Sending…' : 'Request a walkthrough'}
      </button>
      <p className="text-center text-xs text-zinc-500">We&apos;ll only use your information to schedule a walkthrough.</p>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Product-story visuals
// ---------------------------------------------------------------------------

function AgentStage({ orgName }: { orgName: string }) {
  return (
    <div className="launch-product-shadow">
      <div className="launch-product-stage">
        <div className="launch-product-toolbar">
          <div className="flex items-center gap-1.5" aria-hidden="true">
            <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
            <span className="h-2.5 w-2.5 rounded-full bg-white/15" />
          </div>
          <div className="launch-product-title"><Sparkles className="h-3.5 w-3.5" /> {orgName} chat</div>
          <span className="hidden text-[11px] text-zinc-600 sm:block">Agentic workspace</span>
        </div>

        <div className="grid min-h-[480px] grid-cols-1 md:min-h-[560px] md:grid-cols-[178px_minmax(0,1fr)]">
          <aside className="hidden border-r border-white/[0.07] bg-black/20 p-4 md:block" aria-label="Project context">
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-600">Project</p>
            <div className="mt-4 rounded-xl border border-white/[0.07] bg-white/[0.035] p-3">
              <div className="flex items-center gap-2 text-xs text-zinc-300"><FileInput className="h-3.5 w-3.5 text-zinc-500" /> R01 Submission</div>
              <div className="mt-2 text-[11px] text-zinc-600">2026 · 24 documents</div>
            </div>
            <p className="mt-7 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-600">Pinned tools</p>
            <div className="mt-3 space-y-2 text-[11px] text-zinc-500">
              <div className="flex items-center gap-2"><Database className="h-3.5 w-3.5" /> Project knowledge</div>
              <div className="flex items-center gap-2"><GitMerge className="h-3.5 w-3.5" /> NIH compliance</div>
            </div>
          </aside>

          <div className="relative overflow-hidden px-4 py-5 sm:px-7 sm:py-7">
            <div className="launch-chat-prompt">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">You</div>
              <p>Prepare this R01 proposal for compliance review.</p>
            </div>

            <div className="launch-agent-thread">
              <div className="flex items-center gap-2 text-xs font-semibold text-zinc-300">
                <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--highlight-color)_18%,transparent)] text-highlight"><Bot className="h-3.5 w-3.5" /></span>
                {orgName}
              </div>
              <div className="launch-tool-row launch-step-one">
                <ScanLine className="h-4 w-4 text-sky-300" />
                <span className="font-mono text-xs text-sky-200">search_documents</span>
                <span className="ml-auto text-xs text-zinc-500">NIH_R01_Proposal.pdf</span>
                <Check className="h-4 w-4 text-emerald-300" />
              </div>
              <div className="launch-tool-row launch-step-two">
                <PenTool className="h-4 w-4 text-[var(--highlight-color)]" />
                <span className="font-mono text-xs text-[var(--highlight-color)]">run_extraction</span>
                <span className="ml-auto text-xs text-zinc-500">3 fields · quality checked</span>
                <BadgeCheck className="h-4 w-4 text-emerald-300" />
              </div>

              <div className="launch-result-card launch-step-three">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-white">Proposal review is ready.</p>
                    <p className="mt-1 text-xs text-zinc-400">PI, budget, deadline, and policy checks are prepared.</p>
                  </div>
                  <span className="launch-verified-badge"><BadgeCheck className="h-3.5 w-3.5" /> Verified · 94%</span>
                </div>
                <div className="mt-4 grid grid-cols-3 overflow-hidden rounded-xl border border-white/[0.08] bg-black/20 text-center">
                  <div className="border-r border-white/[0.08] p-2.5"><div className="text-sm font-semibold text-white">3</div><div className="mt-0.5 text-[10px] uppercase tracking-[0.1em] text-zinc-500">Fields</div></div>
                  <div className="border-r border-white/[0.08] p-2.5"><div className="text-sm font-semibold text-white">3</div><div className="mt-0.5 text-[10px] uppercase tracking-[0.1em] text-zinc-500">Sources</div></div>
                  <div className="p-2.5"><div className="text-sm font-semibold text-white">12</div><div className="mt-0.5 text-[10px] uppercase tracking-[0.1em] text-zinc-500">Tests</div></div>
                </div>
                <div className="mt-3 flex items-center gap-2 text-xs text-zinc-400"><FileInput className="h-3.5 w-3.5 text-zinc-500" /> OSP Handbook 2026 · p. 47 cited for F&amp;A review</div>
                <div className="mt-4 flex items-center justify-between rounded-lg border border-[color-mix(in_srgb,var(--highlight-color)_38%,transparent)] bg-[color-mix(in_srgb,var(--highlight-color)_9%,transparent)] px-3 py-2.5">
                  <span className="text-xs text-zinc-200">NIH compliance check ready to run</span>
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--highlight-color)]">Review <span aria-hidden="true">→</span></span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function ProjectVisual() {
  return (
    <div className="launch-project-visual">
      <div className="launch-project-visual-header">
        <span className="inline-flex items-center gap-2 text-sm font-semibold text-white"><FileInput className="h-4 w-4 text-[var(--highlight-color)]" /> R01 Submission 2026</span>
        <span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.08em] text-emerald-300">Active</span>
      </div>
      <div className="launch-project-hub">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--highlight-color)_16%,transparent)] text-[var(--highlight-color)]"><FileInput className="h-5 w-5" /></div>
        <div>
          <p className="text-base font-semibold text-white">One project. One shared context.</p>
          <p className="mt-1 text-sm text-zinc-400">24 files · project-wide chat · 4 team members</p>
        </div>
      </div>
      <div className="launch-project-assets">
        <div className="launch-project-asset"><FileInput className="h-4 w-4 text-sky-300" /><span><strong>24 files</strong><small>Auto-indexed for chat</small></span></div>
        <div className="launch-project-asset"><Database className="h-4 w-4 text-violet-300" /><span><strong>Project knowledge</strong><small>Answers grounded in this work</small></span></div>
        <div className="launch-project-asset"><GitMerge className="h-4 w-4 text-[var(--highlight-color)]" /><span><strong>5 pinned tools</strong><small>Workflows and extractions at hand</small></span></div>
        <div className="launch-project-asset"><Users className="h-4 w-4 text-emerald-300" /><span><strong>Shared team space</strong><small>Draft → active → closeout</small></span></div>
      </div>
    </div>
  )
}

function TrustVisual() {
  return (
    <div className="launch-trust-visual">
      <div className="launch-trust-header">
        <span className="font-mono text-xs text-zinc-500">run_extraction · NIH_R01_Proposal.pdf</span>
        <span className="launch-verified-badge"><BadgeCheck className="h-3.5 w-3.5" /> Excellent</span>
      </div>
      <div className="grid grid-cols-3 gap-2.5 sm:gap-3">
        <div className="launch-metric"><strong>94%</strong><span>Accuracy</span></div>
        <div className="launch-metric"><strong>91%</strong><span>Consistency</span></div>
        <div className="launch-metric"><strong>12</strong><span>Test cases</span></div>
      </div>
      <div className="mt-4 rounded-xl border border-zinc-200 bg-white p-4">
        <div className="flex items-center justify-between gap-3"><span className="text-sm font-semibold text-zinc-900">OSP policy match</span><span className="text-xs font-medium text-zinc-500">3 cited sources</span></div>
        <p className="mt-3 text-sm leading-6 text-zinc-600">Subaward budgets over $250,000 require additional F&amp;A review.</p>
        <div className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: 'var(--highlight-on-light, #806600)' }}><FileInput className="h-3.5 w-3.5" /> OSP_Handbook_2026.pdf · p. 47</div>
      </div>
      <p className="mt-4 text-xs text-zinc-500">Last validated 2 days ago · 0 active alerts</p>
    </div>
  )
}

function ConfirmationVisual() {
  return (
    <div className="launch-confirmation-card">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--highlight-color)_13%,white)]" style={{ color: 'var(--highlight-on-light, #806600)' }}><ShieldCheck className="h-5 w-5" /></span>
        <div>
          <p className="text-sm font-semibold text-zinc-900">Ready for your approval</p>
          <p className="mt-1 text-sm leading-6 text-zinc-600">Run the NIH compliance check on NIH_R01_Proposal.pdf?</p>
        </div>
      </div>
      <div className="mt-5 rounded-xl border border-zinc-200 bg-zinc-50 px-3.5 py-3 text-sm text-zinc-600">8 verified steps · policy review, extraction, and report delivery</div>
      <div className="mt-4 flex gap-3">
        <button type="button" className="launch-secondary-button flex-1 justify-center">Not now</button>
        <button type="button" className="launch-brand-button flex-1 justify-center">Review &amp; run</button>
      </div>
    </div>
  )
}

function safeNextPath(raw: string | undefined): string | null {
  if (!raw) return null
  if (!raw.startsWith('/') || raw.startsWith('//')) return null
  return raw
}

export default function Landing() {
  const { user, loading, demoExpired, demoFeedbackToken } = useAuth()
  const branding = useBranding()
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)
  const [accessOpen, setAccessOpen] = useState(false)
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const inviteToken = search?.invite_token
  const nextPath = safeNextPath(search?.next)

  useEffect(() => {
    getAuthConfig()
      .then(setAuthConfig)
      .catch(() => setAuthConfig({ auth_methods: ['password'], oauth_providers: [] }))
  }, [])

  useEffect(() => {
    if (user && !demoExpired && !inviteToken && nextPath) window.location.replace(nextPath)
  }, [user, demoExpired, inviteToken, nextPath])

  if (loading) return null
  if (demoExpired && demoFeedbackToken) return <Navigate to="/demo/trial-end" search={{ token: demoFeedbackToken }} />
  if (user && !demoExpired) {
    if (inviteToken) return <Navigate to="/invite" search={{ token: inviteToken }} />
    if (nextPath) return null
    return <Navigate to="/" search={{ mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined }} />
  }

  const primaryCta = authConfig?.trial_system_enabled ? (
    <Link to="/demo" className="launch-light-button">Try {branding.orgName} <span aria-hidden="true">→</span></Link>
  ) : (
    <a href="#demo" className="launch-light-button">Request a walkthrough <span aria-hidden="true">→</span></a>
  )

  return (
    <div className="landing-page launch-page min-h-screen overflow-x-hidden bg-black text-zinc-100 antialiased">
      <a href="#main-content" className="launch-skip-link">Skip to main content</a>

      <header className="launch-nav">
        <div className="launch-content-wide flex h-16 items-center justify-between gap-5">
          <a href="#top" className="flex min-w-0 items-center" aria-label={`${branding.orgName} home`}>
            <img src={branding.logoDarkUrl} alt={branding.orgName} className="h-9 max-w-[190px] object-contain object-left sm:h-10 sm:max-w-[240px]" />
          </a>
          <nav aria-label="Primary navigation" className="hidden items-center gap-6 md:flex">
            <a href="#agent" className="launch-nav-link">What&apos;s new</a>
            <a href="#projects" className="launch-nav-link">Projects</a>
            <a href="#trust" className="launch-nav-link">Trust</a>
            <Link to="/docs" className="launch-nav-link">Docs</Link>
          </nav>
          <div className="flex shrink-0 items-center gap-3">
            <button type="button" onClick={() => setAccessOpen(true)} className="hidden text-sm font-medium text-zinc-300 transition-colors hover:text-white sm:block">Sign in</button>
            <a href="#demo" className="launch-nav-cta">Get started <span aria-hidden="true">→</span></a>
          </div>
        </div>
      </header>

      <main id="main-content">
        <section id="top" className="launch-hero">
          <div className="launch-hero-glow launch-hero-glow-one" aria-hidden="true" />
          <div className="launch-hero-glow launch-hero-glow-two" aria-hidden="true" />
          <div className="launch-content-wide relative z-10 flex flex-col items-center pt-32 text-center sm:pt-40">
            <p className="launch-eyebrow"><Sparkles className="h-4 w-4" /> Platform update · 5.0</p>
            <h1 className="launch-display mt-7 max-w-5xl">Everything {branding.orgName} can do. <span>Now, you just ask.</span></h1>
            <p className="mt-7 max-w-2xl text-lg leading-8 text-zinc-400 sm:text-xl">Search documents. Build knowledge. Extract what matters. Launch verified workflows. See every source, score, and approval along the way.</p>
            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              {primaryCta}
              <a href="#agent" className="launch-ghost-button">See how it works <ArrowDown className="h-4 w-4" /></a>
            </div>
            <p className="mt-5 text-sm text-zinc-500">A trusted agentic workspace for research administration.</p>
          </div>
          <div className="launch-content-wide relative z-10 mt-16 pb-8 sm:mt-20 sm:pb-12">
            <AgentStage orgName={branding.orgName} />
          </div>
        </section>

        <section id="agent" className="launch-capability-section" aria-labelledby="capabilities-heading">
          <div className="launch-content-wide">
            <div className="mx-auto max-w-3xl text-center">
              <p className="launch-eyebrow"><MessageSquare className="h-4 w-4" /> One conversation</p>
              <h2 id="capabilities-heading" className="launch-heading mt-5">The whole system, <span>one conversation.</span></h2>
              <p className="mt-5 text-lg leading-8 text-zinc-400">The agent doesn&apos;t sit beside the platform. It is the way your team reaches every part of it.</p>
            </div>
            <div className="launch-capability-rail mt-14">
              <article className="launch-capability-card"><span className="launch-card-number">01</span><ScanLine className="h-7 w-7" /><h3>Find</h3><p>Search a workspace, folder, document, or policy library in your own words.</p></article>
              <article className="launch-capability-card"><span className="launch-card-number">02</span><Database className="h-7 w-7" /><h3>Know</h3><p>Ask institutional knowledge bases questions and follow the cited source.</p></article>
              <article className="launch-capability-card"><span className="launch-card-number">03</span><PenTool className="h-7 w-7" /><h3>Extract</h3><p>Turn unstructured proposals into review-ready data with quality in view.</p></article>
              <article className="launch-capability-card"><span className="launch-card-number">04</span><GitMerge className="h-7 w-7" /><h3>Run</h3><p>Start the verified workflow your office already trusts—right from chat.</p></article>
              <article className="launch-capability-card"><span className="launch-card-number">05</span><BadgeCheck className="h-7 w-7" /><h3>Verify</h3><p>Build test cases, validate results, and make trust visible over time.</p></article>
            </div>
          </div>
        </section>

        <section id="projects" className="launch-project-section" aria-labelledby="projects-heading">
          <div className="launch-content-wide grid items-center gap-14 lg:grid-cols-[minmax(0,0.93fr)_minmax(0,1.07fr)] lg:gap-24">
            <div>
              <p className="launch-eyebrow"><FileInput className="h-4 w-4" /> Projects</p>
              <h2 id="projects-heading" className="launch-heading mt-5">One piece of work. <span>One shared place.</span></h2>
              <p className="mt-6 max-w-xl text-lg leading-8 text-zinc-400">A Project gives every grant, award, contract, or review a scoped home. Its files, project-wide chat, trusted tools, and team context all stay together.</p>
              <div className="mt-9 space-y-4 text-sm leading-6 text-zinc-300">
                <div className="flex gap-3"><Check className="mt-1 h-4 w-4 shrink-0 text-[var(--highlight-color)]" /><span>Files are automatically indexed, so project-wide chat is ready from the first upload.</span></div>
                <div className="flex gap-3"><Check className="mt-1 h-4 w-4 shrink-0 text-[var(--highlight-color)]" /><span>Pin the workflows, extraction templates, and automations this work needs most.</span></div>
                <div className="flex gap-3"><Check className="mt-1 h-4 w-4 shrink-0 text-[var(--highlight-color)]" /><span>Keep the right people in context as the work moves from draft to closeout.</span></div>
              </div>
            </div>
            <ProjectVisual />
          </div>
        </section>

        <section id="trust" className="launch-trust-section" aria-labelledby="trust-heading">
          <div className="launch-content-wide grid items-center gap-14 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:gap-24">
            <div>
              <p className="launch-eyebrow launch-eyebrow-dark"><BadgeCheck className="h-4 w-4" /> The trust layer</p>
              <h2 id="trust-heading" className="launch-heading-dark mt-6">It doesn&apos;t just answer. <span>It shows its work.</span></h2>
              <p className="mt-7 max-w-xl text-lg leading-8 text-zinc-600">Generic chat is built to sound useful. {branding.orgName} is built for the work where you need to know why an answer deserves your confidence.</p>
              <div className="mt-10 space-y-7">
                <div className="launch-proof"><FileInput className="h-5 w-5" /><div><h3>Cited answers</h3><p>Follow a knowledge-base answer to the exact passage that supports it.</p></div></div>
                <div className="launch-proof"><BadgeCheck className="h-5 w-5" /><div><h3>Quality you can see</h3><p>Accuracy, consistency, test cases, and active alerts stay with the result.</p></div></div>
                <div className="launch-proof"><RefreshCw className="h-5 w-5" /><div><h3>Trust that improves</h3><p>Guided verification turns real work into stronger, reusable templates.</p></div></div>
              </div>
            </div>
            <TrustVisual />
          </div>
        </section>

        <section className="launch-control-section" aria-labelledby="control-heading">
          <div className="launch-content-wide grid items-center gap-14 lg:grid-cols-[minmax(0,1.08fr)_minmax(0,0.92fr)] lg:gap-24">
            <ConfirmationVisual />
            <div>
              <p className="launch-eyebrow"><ShieldCheck className="h-4 w-4" /> Human control, built in</p>
              <h2 id="control-heading" className="launch-heading mt-5">The agent acts. <span>You stay in control.</span></h2>
              <p className="mt-6 text-lg leading-8 text-zinc-400">Every meaningful write is previewed before it happens. You approve workflow runs, knowledge-base changes, validation, and new templates—without leaving the conversation.</p>
              <div className="mt-9 grid gap-3 sm:grid-cols-2">
                <div className="launch-control-point"><ShieldCheck className="h-5 w-5" /><span>Explicit approval gates</span></div>
                <div className="launch-control-point"><Users className="h-5 w-5" /><span>Team-based access</span></div>
                <div className="launch-control-point"><Lock className="h-5 w-5" /><span>Private workspaces</span></div>
                <div className="launch-control-point"><CheckCircle className="h-5 w-5" /><span>Auditable actions</span></div>
              </div>
            </div>
          </div>
        </section>

        <section id="demo" className="launch-demo-section" aria-labelledby="demo-heading">
          <div className="launch-content-wide grid items-start gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-24">
            <div>
              <p className="launch-eyebrow"><Sparkles className="h-4 w-4" /> See 5.0 in action</p>
              <h2 id="demo-heading" className="launch-heading mt-6">Your office has a better way to work.</h2>
              <p className="mt-6 max-w-lg text-lg leading-8 text-zinc-400">Bring a real proposal, policy question, or review workflow. We&apos;ll show you what an agentic {branding.orgName} experience can look like for your team.</p>
              {authConfig?.trial_system_enabled && <div className="mt-8">{primaryCta}</div>}
              <div className="launch-demo-credentials"><span>Built for research administration</span><span>Open source · self-hosted</span></div>
            </div>
            <DemoRequestForm />
          </div>
        </section>
      </main>

      {accessOpen && <AccessDialog config={authConfig} orgName={branding.orgName} onClose={() => setAccessOpen(false)} />}
      <Footer />
    </div>
  )
}
