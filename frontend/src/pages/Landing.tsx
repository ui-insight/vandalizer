import { useState, useEffect, type FormEvent } from 'react'
import { Link, Navigate, useSearch } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { getAuthConfig, type AuthConfig } from '../api/auth'
import { Footer } from '../components/layout/Footer'
import {
  Check,
  ShieldCheck,
  Loader2,
  GitMerge,
  CheckCircle,
  Users,
  Lock,
  RefreshCw,
  ArrowDown,
  GraduationCap,
  ExternalLink,
  MessageSquare,
  Sparkles,
  Award,
  Bot,
  Database,
  PlayCircle,
  BadgeCheck,
  FileInput,
  ScanLine,
  PenTool,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Inline dark-themed auth forms
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
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
      />
      <input
        type="password"
        placeholder="Password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
      />
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-lg bg-highlight px-4 py-3 font-bold text-highlight-text transition-all hover:bg-highlight-hover disabled:opacity-50"
      >
        {submitting ? 'Signing in...' : 'SIGN IN'}
      </button>
      <p className="text-center text-sm">
        <Link to="/reset-password" search={{ token: undefined }} className="text-gray-400 hover:text-highlight transition-colors">
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
      // user_id = email, matching Flask behavior
      await register(email, email, password, name || undefined, undefined, role || undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 w-full max-w-sm mx-auto">
      {error && (
        <div className="rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
          {error}
        </div>
      )}
      <input
        type="text"
        placeholder="Full Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
      />
      <input
        type="email"
        placeholder="Email Address"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
      />
      <input
        type="password"
        placeholder="Password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
      />
      <select
        value={role}
        onChange={(e) => setRole(e.target.value)}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
      >
        <option value="">Your role (optional)</option>
        <option value="research_admin">Research Administrator</option>
        <option value="pi">Principal Investigator</option>
        <option value="sponsored_programs">Sponsored Programs / OSP</option>
        <option value="compliance">Compliance</option>
        <option value="it">IT / Systems</option>
        <option value="other">Other</option>
      </select>
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-lg bg-highlight px-4 py-3 font-bold text-highlight-text transition-all hover:bg-highlight-hover disabled:opacity-50"
      >
        {submitting ? 'Creating account...' : 'CREATE ACCOUNT'}
      </button>
      <p className="text-center text-sm text-gray-400">
        Already have an account?{' '}
        <button type="button" onClick={onSwitch} className="font-bold text-white hover:text-highlight">
          Sign in
        </button>
      </p>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Optional demo video — plugs in a real screencast when teams have one.
// Set VITE_DEMO_VIDEO_URL in the frontend env to render. Supports either a
// direct .mp4 URL (uses <video>) or a YouTube/Vimeo embed URL (uses <iframe>).
// ---------------------------------------------------------------------------

function DemoVideo() {
  const url = (import.meta.env.VITE_DEMO_VIDEO_URL as string | undefined)?.trim()
  if (!url) return null

  const isIframeEmbed =
    /youtube\.com\/embed\//.test(url) ||
    /player\.vimeo\.com\/video\//.test(url) ||
    /loom\.com\/embed\//.test(url)

  return (
    <section className="relative z-10 pt-24 pb-8">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-highlight/10 border border-highlight/20 mb-4">
            <PlayCircle className="w-5 h-5 text-highlight" />
            <span className="text-sm font-bold text-highlight uppercase tracking-wider">
              Two-Minute Walkthrough
            </span>
          </div>
          <h2 className="text-3xl font-bold text-white">See it drive a real research-admin workflow</h2>
        </div>
        <div className="relative rounded-2xl border border-white/10 overflow-hidden shadow-2xl aspect-video bg-black">
          {isIframeEmbed ? (
            <iframe
              src={url}
              title="Vandalizer demo"
              className="absolute inset-0 w-full h-full"
              frameBorder={0}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          ) : (
            <video
              src={url}
              controls
              playsInline
              className="absolute inset-0 w-full h-full object-cover"
            />
          )}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Demo Request Form
// ---------------------------------------------------------------------------

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
      <div className="max-w-xl mx-auto rounded-2xl border border-green-500/30 bg-green-500/5 px-8 py-10 text-center">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-green-500/10 text-green-400 mb-4">
          <Check className="w-6 h-6" />
        </div>
        <h3 className="text-2xl font-bold text-white mb-2">Thanks — we&apos;ll be in touch soon.</h3>
        <p className="text-gray-400">
          Someone from the Vandalizer team will reach out within one business day to schedule your walkthrough.
        </p>
      </div>
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="max-w-xl mx-auto glass-panel rounded-2xl border border-white/10 p-6 md:p-8 text-left space-y-4"
    >
      {error && (
        <div className="rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
          {error}
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <input
          type="text"
          required
          placeholder="Your name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
        />
        <input
          type="email"
          required
          placeholder="Work email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
        />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <input
          type="text"
          required
          placeholder="Institution / organization"
          value={institution}
          onChange={(e) => setInstitution(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
        />
        <select
          required
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50"
        >
          <option value="" disabled>Your role</option>
          <option value="research_admin">Research Administrator</option>
          <option value="pi">Principal Investigator</option>
          <option value="sponsored_programs">Sponsored Programs / OSP</option>
          <option value="compliance">Compliance</option>
          <option value="it">IT / Systems</option>
          <option value="other">Other</option>
        </select>
      </div>
      <textarea
        placeholder="What would you like to see in the demo? (optional)"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={3}
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-highlight/50 focus:outline-none focus:ring-1 focus:ring-highlight/50 resize-none"
      />
      <button
        type="submit"
        disabled={submitting}
        className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-white text-black px-8 py-3 font-bold text-lg transition-all hover:bg-gray-200 disabled:opacity-50 shadow-[0_0_20px_rgba(255,255,255,0.15)]"
      >
        <PlayCircle className="w-5 h-5" />
        {submitting ? 'Sending…' : 'Request a Demo'}
      </button>
      <p className="text-xs text-gray-500 text-center">
        We&apos;ll only use your info to schedule a walkthrough. No spam, no lists.
      </p>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Auth block — combines OAuth + password forms
// ---------------------------------------------------------------------------

function AuthBlock({ config }: { config: AuthConfig | null }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const oauthError = search?.error
  const adminOverride = search?.admin === '1'

  if (!config) {
    return (
      <div className="flex justify-center py-8">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-highlight border-t-transparent" />
      </div>
    )
  }

  const oauthEnabled = config.auth_methods.includes('oauth')
  const passwordEnabled = config.auth_methods.includes('password') || adminOverride
  const azureProvider = config.oauth_providers.find(
    (p) => p.provider === 'azure' && p.configured,
  )
  const samlProvider = config.oauth_providers.find(
    (p) => p.provider === 'saml',
  )

  return (
    <div className="mt-8 w-full max-w-sm mx-auto">
      {oauthError && (
        <div className="mb-4 rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
          Authentication failed. Please try again.
        </div>
      )}

      {oauthEnabled && azureProvider && (
        <div className="mb-6">
          <a
            href="/api/auth/oauth/azure"
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-white px-4 py-3 font-bold text-black transition-all hover:bg-gray-200"
          >
            {azureProvider.display_name}
          </a>
        </div>
      )}

      {samlProvider && (
        <div className="mb-6">
          <a
            href="/api/auth/saml/login"
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-highlight px-4 py-3 font-bold text-highlight-text transition-all hover:bg-highlight-hover"
          >
            {samlProvider.display_name || 'Sign in with University SSO'}
          </a>
        </div>
      )}

      {oauthEnabled && azureProvider && passwordEnabled && (
        <div className="relative mb-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-white/10" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="bg-[#0a0a0a] px-4 text-gray-500">or</span>
          </div>
        </div>
      )}

      {passwordEnabled && (
        <>
          {mode === 'login' ? (
            <>
              <LandingLoginForm />
              <p className="mt-4 text-center text-sm text-gray-400">
                Don&apos;t have an account?{' '}
                <button
                  onClick={() => setMode('register')}
                  className="font-bold text-white hover:text-highlight"
                >
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
        <p className="mt-6 text-center text-sm text-gray-400">
          Have a trial account?{' '}
          <Link to="/login" className="font-bold text-white hover:text-highlight">
            Log in here
          </Link>
        </p>
      )}

    </div>
  )
}

// ---------------------------------------------------------------------------
// Landing page
// ---------------------------------------------------------------------------

export default function Landing() {
  const { user, loading, demoExpired, demoFeedbackToken } = useAuth()
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const inviteToken = search?.invite_token

  useEffect(() => {
    getAuthConfig().then(setAuthConfig)
  }, [])

  if (loading) return null
  if (user && demoExpired && demoFeedbackToken) {
    return <Navigate to="/demo/feedback" search={{ token: demoFeedbackToken }} />
  }
  if (user && !demoExpired) {
    // If user arrived here with an invite token, redirect to accept it
    if (inviteToken) {
      return <Navigate to="/invite" search={{ token: inviteToken }} />
    }
    return (
      <Navigate
        to="/"
        search={{
          mode: undefined,
          tab: undefined,
          workflow: undefined,
          extraction: undefined,
          automation: undefined,
          kb: undefined,
        }}
      />
    )
  }

  return (
    <div className="landing-page bg-[#0a0a0a] text-gray-200 antialiased w-full min-h-screen relative">
      {/* Fixed top nav */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <img src="/images/Vandalizer_Wordmark_Color_RGB+W.png" alt="Vandalizer" className="h-10" />
          <div className="flex items-center gap-4">
            <Link
              to="/docs"
              className="text-sm text-gray-400 hover:text-highlight transition-colors"
            >
              Docs
            </Link>
            <a
              href="https://github.com/ui-insight/vandalizer"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-highlight transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              GitHub
            </a>
          </div>
        </div>
      </nav>

      {/* Background Ambient Glow */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-yellow-600/10 rounded-full blur-[120px] animate-pulse" />
        <div
          className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-gray-800/30 rounded-full blur-[120px] animate-pulse"
          style={{ animationDelay: '2s' }}
        />
      </div>

      {/* Hero */}
      <div className="relative z-10 pt-32 pb-8 border-t border-white/5">
        {/* Tech Wave Background */}
        <div className="absolute top-[150px] left-0 w-full h-[350px] z-0 pointer-events-none opacity-25">
          <svg
            className="w-full h-full"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 24 150 28"
            preserveAspectRatio="none"
          >
            <defs>
              <path
                id="tech-line"
                d="M-160 44c30 0 58-18 88-18s 58 18 88 18 58-18 88-18 58 18 88 18"
              />
            </defs>
            <g className="tech-wave stroke-highlight">
              <use xlinkHref="#tech-line" x="48" y="0" fill="none" strokeWidth="0.3" />
              <use xlinkHref="#tech-line" x="48" y="3" fill="none" strokeWidth="0.5" />
              <use xlinkHref="#tech-line" x="48" y="5" fill="none" strokeWidth="0.2" />
              <use xlinkHref="#tech-line" x="48" y="7" fill="none" strokeWidth="0.1" />
              <use xlinkHref="#tech-line" x="48" y="12" fill="none" strokeWidth="0.4" />
              <use xlinkHref="#tech-line" x="48" y="20" fill="none" strokeWidth="0.15" />
            </g>
          </svg>
        </div>

        <div className="relative z-10 flex flex-col items-center text-center px-4">
          {/* v5.0 Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-highlight/10 border border-highlight/20 mb-10 hover:bg-highlight/20 transition-colors cursor-default">
            <Sparkles className="w-4 h-4 text-highlight" />
            <span className="text-sm font-bold text-highlight tracking-wide uppercase">
              Vandalizer 5.0 — Fully Agentic
            </span>
          </div>

          {/* Logo */}
          <img
            src="/images/Vandalizer_Wordmark_Color_RGB+W.png"
            alt="Vandalizer"
            className="w-full max-w-[500px] mb-5"
          />

          {/* Tagline */}
          <p className="text-2xl md:text-3xl text-white max-w-3xl mx-auto leading-tight mb-4 font-bold">
            Chat with your research documents.
            <br />
            <span className="text-highlight">Every answer is validated.</span>
          </p>
          <p className="text-lg md:text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed mb-8">
            Run extractions, build knowledge bases, and orchestrate workflows — all from one conversation. Backed by verified test cases and quality scores you can trust.
          </p>

          {/* Demo CTA */}
          {authConfig?.trial_system_enabled && (
            <div className="mb-8">
              <Link
                to="/demo"
                className="inline-flex items-center gap-2 rounded-full bg-white/10 border border-white/20 px-6 py-3 font-bold text-white transition-all hover:bg-white/20 hover:border-highlight/30"
              >
                Try the Free Trial
                <span className="text-highlight">&rarr;</span>
              </Link>
            </div>
          )}

          {/* Auth Block */}
          <AuthBlock config={authConfig} />
        </div>
      </div>

      {/* Hero Visualization — Agentic Chat Mock */}
      <main className="relative z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="mt-24 relative mx-auto max-w-4xl hidden md:block" style={{ animation: 'float 6s ease-in-out infinite' }}>
            <div className="absolute -inset-1 bg-gradient-to-r from-highlight-hover to-yellow-600 rounded-xl blur opacity-20" />
            <div className="relative glass-panel rounded-xl border border-white/10 overflow-hidden shadow-2xl text-left">
              {/* Window chrome */}
              <div className="flex items-center px-4 py-3 border-b border-white/5 bg-black/40">
                <div className="flex space-x-2">
                  <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/50" />
                  <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/50" />
                  <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/50" />
                </div>
                <div className="ml-4 text-xs text-gray-500 font-mono">Vandalizer — Chat</div>
              </div>

              {/* Chat body */}
              <div className="p-6 space-y-4 text-sm">
                {/* User message */}
                <div className="flex justify-end">
                  <div className="max-w-md rounded-xl rounded-br-sm bg-highlight/10 border border-highlight/20 px-4 py-3 text-gray-200">
                    Extract PI name, budget, and deadline from the NIH R01 proposal in the grants folder.
                  </div>
                </div>

                {/* Agent: tool call — search_documents */}
                <div className="flex items-start gap-3">
                  <div className="shrink-0 mt-1 p-1.5 rounded-lg bg-highlight/10 text-highlight">
                    <Bot className="w-4 h-4" />
                  </div>
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2 text-xs text-gray-400">
                      <Check className="w-3 h-3 text-green-500" />
                      <span className="font-mono text-gray-400">search_documents</span>
                      <span className="text-gray-500">— found 1 match: NIH_R01_Proposal.pdf</span>
                    </div>

                    {/* Tool call — run_extraction */}
                    <div className="flex items-center gap-2 text-xs text-gray-400">
                      <Check className="w-3 h-3 text-green-500" />
                      <span className="font-mono text-orange-400">run_extraction</span>
                      <span className="text-gray-500">— 3 fields extracted</span>
                      {/* Quality badge */}
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/30 text-green-400 text-[10px] font-bold uppercase tracking-wide">
                        <BadgeCheck className="w-3 h-3" />
                        Verified · 94%
                      </span>
                    </div>

                    {/* Result table */}
                    <div className="bg-[#1a1a1a] border border-white/5 rounded-lg overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-black/40 text-gray-500 uppercase tracking-wider">
                          <tr>
                            <th className="text-left px-3 py-2 font-semibold">Field</th>
                            <th className="text-left px-3 py-2 font-semibold">Value</th>
                          </tr>
                        </thead>
                        <tbody className="text-gray-300 font-mono">
                          <tr className="border-t border-white/5">
                            <td className="px-3 py-2 text-gray-400">PI Name</td>
                            <td className="px-3 py-2">Dr. Maya Chen</td>
                          </tr>
                          <tr className="border-t border-white/5">
                            <td className="px-3 py-2 text-gray-400">Budget</td>
                            <td className="px-3 py-2">$2,489,000</td>
                          </tr>
                          <tr className="border-t border-white/5">
                            <td className="px-3 py-2 text-gray-400">Deadline</td>
                            <td className="px-3 py-2">Feb 5, 2026</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    <p className="text-gray-300 pt-1">
                      Extraction complete — validated against 12 test cases with 94% accuracy. Want me to check compliance against your NIH checklist workflow?
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        {/* Grid Background Effect */}
        <div className="absolute inset-0 grid-bg -z-10 opacity-20" />
      </main>

      {/* Optional demo video — renders only when VITE_DEMO_VIDEO_URL is set */}
      <DemoVideo />

      {/* Chat That Earns Your Trust */}
      <section className="py-32 relative border-t border-white/5 bg-[#171717]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col lg:flex-row gap-16 items-center">
            <div className="w-full lg:w-1/2">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-highlight/10 border border-highlight/20 mb-8">
                <BadgeCheck className="w-5 h-5 text-highlight" />
                <span className="text-sm font-bold text-highlight uppercase tracking-wider">
                  The Trust Layer
                </span>
              </div>
              <h2 className="text-4xl md:text-5xl font-bold text-white mb-8 leading-tight">
                Chat you can <span className="text-highlight">trust</span>,<br />
                not just chat that&apos;s <span className="text-gray-500 line-through">convenient</span>.
              </h2>
              <p className="text-xl text-gray-400 leading-relaxed mb-8">
                Generic AI chat works for one-off questions. Research administration doesn&apos;t tolerate &ldquo;usually right.&rdquo; Vandalizer pairs conversational ease with verified test cases, quality scores, and source-linked answers — so every reply shows you <em>how</em> it knows.
              </p>
              <div className="space-y-6">
                <div className="flex gap-4">
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10 h-fit">
                    <BadgeCheck className="w-6 h-6 text-highlight" />
                  </div>
                  <div>
                    <h4 className="text-xl font-bold text-white mb-2">Quality scores on every result</h4>
                    <p className="text-lg text-gray-400">
                      Accuracy, consistency, and test-case counts surface inline — not buried in a dashboard.
                    </p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10 h-fit">
                    <ShieldCheck className="w-6 h-6 text-highlight" />
                  </div>
                  <div>
                    <h4 className="text-xl font-bold text-white mb-2">Source-linked answers</h4>
                    <p className="text-lg text-gray-400">
                      Click any passage in a knowledge-base reply to jump straight to the document at the cited line.
                    </p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10 h-fit">
                    <CheckCircle className="w-6 h-6 text-highlight" />
                  </div>
                  <div>
                    <h4 className="text-xl font-bold text-white mb-2">Guided verification</h4>
                    <p className="text-lg text-gray-400">
                      Turn any extraction into a test case in one click. The more you use it, the more trustworthy it gets.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Quality signal visual */}
            <div className="w-full lg:w-1/2">
              <div className="relative">
                <div className="glass-panel p-6 rounded-xl border border-white/10 mb-4">
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-sm font-mono text-gray-500">run_extraction · NIH_R01_Proposal.pdf</span>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/30 text-green-400 text-[10px] font-bold uppercase tracking-wide">
                      <BadgeCheck className="w-3 h-3" /> Excellent
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="rounded-lg bg-black/40 border border-white/5 p-3">
                      <div className="text-3xl font-bold text-green-400">94%</div>
                      <div className="text-xs text-gray-500 mt-1 uppercase tracking-wide">Accuracy</div>
                    </div>
                    <div className="rounded-lg bg-black/40 border border-white/5 p-3">
                      <div className="text-3xl font-bold text-highlight">91%</div>
                      <div className="text-xs text-gray-500 mt-1 uppercase tracking-wide">Consistency</div>
                    </div>
                    <div className="rounded-lg bg-black/40 border border-white/5 p-3">
                      <div className="text-3xl font-bold text-white">12</div>
                      <div className="text-xs text-gray-500 mt-1 uppercase tracking-wide">Test Cases</div>
                    </div>
                  </div>
                  <div className="mt-4 text-xs text-gray-500 font-mono">
                    last validated · 2 days ago · 3 runs · 0 active alerts
                  </div>
                </div>
                <div className="glass-panel p-6 rounded-xl border border-white/10 bg-[#262626]">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-sm font-mono text-gray-500">search_knowledge_base · OSP Handbook</span>
                    <span className="px-2 py-1 rounded bg-blue-500/20 text-blue-400 text-xs font-bold">
                      3 SOURCES
                    </span>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="rounded bg-black/40 border border-white/5 p-3">
                      <div className="text-xs text-gray-500 font-mono mb-1">📄 OSP_Handbook_2026.pdf · p. 47</div>
                      <div className="text-gray-300">&ldquo;Subaward budgets exceeding $250,000 require additional F&amp;A review…&rdquo;</div>
                    </div>
                    <div className="flex items-center gap-2 text-blue-400 text-xs">
                      <Loader2 className="w-3 h-3 animate-spin" /> Cross-referencing 2 more sources…
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Workflows */}
      <section className="py-32 relative border-t border-white/5 bg-black">
        <div className="absolute inset-0 grid-bg opacity-30" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col lg:flex-row-reverse gap-16 items-center">
            <div className="w-full lg:w-1/2">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-500/10 border border-blue-500/20 mb-8">
                <GitMerge className="w-5 h-5 text-blue-400" />
                <span className="text-sm font-bold text-blue-400 uppercase tracking-wider">
                  Workflows, on Command
                </span>
              </div>
              <h2 className="text-4xl md:text-5xl font-bold text-white mb-8 leading-tight">
                Your verified workflows, <br />
                <span className="text-blue-400">invoked by conversation.</span>
              </h2>
              <p className="text-xl text-gray-400 leading-relaxed mb-8">
                No more hunting for the right workflow in a menu. Ask the agent to run your NIH compliance check, your subaward review, or your custom pipeline — and watch each step execute live, with approval gates and quality signals intact.
              </p>
              <ul className="space-y-4">
                {[
                  'Ask in plain English — the agent picks the right workflow',
                  'Live step-by-step status while workflows execute',
                  'Approval gates still pause for human review',
                  'Build new workflows from chat: describe the process, refine, verify',
                ].map((text) => (
                  <li key={text} className="flex items-center gap-4 text-lg text-gray-300">
                    <CheckCircle className="w-6 h-6 text-blue-500" />
                    <span>{text}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Workflow diagram visual */}
            <div className="w-full lg:w-1/2">
              <div className="glass-panel p-8 rounded-2xl border border-white/10 relative">
                <div className="flex flex-col items-center gap-4">
                  <div className="w-full p-4 rounded-lg bg-[#262626] border border-white/10 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded bg-white/5">
                        <FileInput className="w-5 h-5 text-gray-400" />
                      </div>
                      <span className="font-mono text-sm text-gray-300">Input: RFP.pdf</span>
                    </div>
                  </div>

                  <ArrowDown className="w-6 h-6 text-gray-600" />

                  <div
                    className="w-full p-4 rounded-lg bg-[#262626] border border-highlight/30 flex items-center justify-between"
                    style={{ boxShadow: '0 0 15px color-mix(in srgb, var(--highlight-color) 10%, transparent)' }}
                  >
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded bg-highlight/10">
                        <ScanLine className="w-5 h-5 text-highlight" />
                      </div>
                      <span className="font-mono text-sm text-white">
                        Task: Extract Requirements
                      </span>
                    </div>
                    <Check className="w-4 h-4 text-green-500" />
                  </div>

                  <ArrowDown className="w-6 h-6 text-gray-600" />

                  <div className="w-full p-4 rounded-lg bg-[#262626] border border-blue-500/30 flex items-center justify-between shadow-[0_0_15px_rgba(59,130,246,0.1)]">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded bg-blue-500/10">
                        <PenTool className="w-5 h-5 text-blue-400" />
                      </div>
                      <span className="font-mono text-sm text-white">Task: Draft Outline</span>
                    </div>
                    <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Bento Grid */}
      <section className="py-24 relative">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="mb-20 text-center">
            <h2 className="text-4xl font-bold text-white mb-6">Everything your research team needs, from one chat.</h2>
            <p className="text-xl text-gray-400 max-w-2xl mx-auto">
              Documents, knowledge bases, extractions, workflows — all reachable through conversation, all backed by validated quality.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Feature 1: Agentic chat (large) */}
            <div className="col-span-1 md:col-span-2 glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-highlight/10 text-highlight">
                  <MessageSquare className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">01</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-highlight transition-colors relative z-10">
                One chat, every capability
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed mb-6 relative z-10 max-w-lg">
                Search documents, query knowledge bases, run extractions, dispatch workflows, and build new test cases — all through natural conversation. 19 agent tools working behind one prompt.
              </p>
              <div className="absolute -bottom-6 -right-6 w-40 h-40 bg-highlight/5 rounded-full blur-2xl group-hover:bg-highlight/10 transition-colors" />
            </div>

            {/* Feature 2: Knowledge bases */}
            <div className="glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-blue-500/10 text-blue-400">
                  <Database className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">02</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-blue-400 transition-colors relative z-10">
                Institutional knowledge bases
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed relative z-10">
                Build a private KB from your OSP handbook, NIH guides, and internal policies. The agent cites sources inline.
              </p>
            </div>

            {/* Feature 3: Private & Secure */}
            <div className="glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-gray-700/30 text-gray-300">
                  <Lock className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">03</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-gray-300 transition-colors relative z-10">
                Private & secure
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed relative z-10">
                Your documents stay in your tenant. Models don&apos;t train on your data. Role-based access built in.
              </p>
            </div>

            {/* Feature 4: Reproducible */}
            <div className="glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-gray-700/30 text-gray-300">
                  <RefreshCw className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">04</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-gray-300 transition-colors relative z-10">
                Reproducible by design
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed relative z-10">
                Every workflow produces the same result for the same input. No prompt drift, no variability — just auditable processes.
              </p>
            </div>

            {/* Feature 5: Team collaboration */}
            <div className="glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-gray-700/30 text-gray-300">
                  <Users className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">05</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-gray-300 transition-colors relative z-10">
                Team workspaces
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed relative z-10">
                Share verified workflows, KBs, and extraction templates across your office. Roles scope what each member sees.
              </p>
            </div>

            {/* Feature 6: Verify Once */}
            <div className="glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-highlight/10 text-highlight">
                  <BadgeCheck className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">06</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-highlight transition-colors relative z-10">
                Verify once, deploy with confidence
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed relative z-10 max-w-lg">
                Golden-set validation with unified accuracy and consistency scoring. Quality tiers flow inline with every chat reply.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-24 border-t border-white/5 bg-[#171717]/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row gap-12 items-center">
            <div className="w-full md:w-1/2">
              <h2 className="text-4xl font-bold text-white mb-6">
                Ask. The agent acts.
                <br />
                <span className="text-highlight">You keep control.</span>
              </h2>
              <div className="space-y-8">
                {[
                  {
                    n: 1,
                    title: 'Ask in plain English',
                    desc: '“Extract PI, budget, and deadline from the NIH proposal.” The agent picks the right tools — search, extract, validate.',
                  },
                  {
                    n: 2,
                    title: 'Watch it work, live',
                    desc: 'Tool calls stream in real time with source links, quality badges, and confirmation prompts before any write or workflow runs.',
                  },
                  {
                    n: 3,
                    title: 'Trust, then export',
                    desc: 'Every answer shows its evidence and score. Export to CSV, share with your team, or promote the result into a test case.',
                  },
                ].map((step) => (
                  <div key={step.n} className="flex gap-6">
                    <div className="w-10 h-10 rounded-full bg-highlight/20 flex items-center justify-center text-lg font-bold text-highlight shrink-0">
                      {step.n}
                    </div>
                    <div>
                      <h4 className="text-xl font-bold text-white mb-2">{step.title}</h4>
                      <p className="text-gray-400 text-lg">{step.desc}</p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-12">
                <blockquote className="border-l-4 border-highlight pl-6 italic text-gray-300 text-xl leading-relaxed">
                  &ldquo;Vandalizer allows RAs to leverage their institutional knowledge to create
                  flexible workflows targeted at common issues.&rdquo;
                </blockquote>
              </div>
            </div>

            {/* How-it-works visual — agent action stream */}
            <div className="w-full md:w-1/2">
              <div className="glass-panel p-8 rounded-2xl border border-white/10 relative overflow-hidden">
                <div className="absolute inset-0 grid-bg opacity-30" />
                <div className="relative z-10 flex flex-col gap-5 text-sm">

                  {/* User prompt */}
                  <div className="flex items-center gap-4 p-4 rounded-xl bg-[#262626] border border-white/5">
                    <div className="p-3 rounded-lg bg-white/10 text-white">
                      <MessageSquare className="w-5 h-5" />
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-mono text-gray-500 mb-1">user</div>
                      <div className="text-white">&ldquo;Run NIH compliance check on the R01 proposal.&rdquo;</div>
                    </div>
                  </div>

                  <div className="flex justify-center -my-2">
                    <ArrowDown className="w-5 h-5 text-gray-600" />
                  </div>

                  {/* Agent tool calls */}
                  <div className="relative p-5 rounded-xl bg-[#0a0a0a] border border-highlight/30 space-y-2.5"
                    style={{ boxShadow: '0 0 30px color-mix(in srgb, var(--highlight-color) 10%, transparent)' }}>
                    <div className="flex items-center gap-2">
                      <Bot className="w-4 h-4 text-highlight" />
                      <span className="text-xs font-mono text-highlight">agent</span>
                    </div>
                    <div className="flex items-center gap-2 font-mono text-xs">
                      <Check className="w-3 h-3 text-green-500" />
                      <span className="text-blue-400">search_documents</span>
                      <span className="text-gray-500">— 1 result</span>
                    </div>
                    <div className="flex items-center gap-2 font-mono text-xs">
                      <Check className="w-3 h-3 text-green-500" />
                      <span className="text-purple-400">run_workflow</span>
                      <span className="text-gray-500">— NIH Compliance · 8/8 steps</span>
                    </div>
                    <div className="flex items-center gap-2 font-mono text-xs">
                      <Loader2 className="w-3 h-3 animate-spin text-highlight" />
                      <span className="text-orange-400">run_extraction</span>
                      <span className="text-gray-500">— finalizing…</span>
                    </div>
                  </div>

                  <div className="flex justify-center -my-2">
                    <ArrowDown className="w-5 h-5 text-gray-600" />
                  </div>

                  {/* Verified output */}
                  <div className="flex items-center gap-4 p-4 rounded-xl bg-[#262626] border border-green-500/20">
                    <div className="p-3 rounded-lg bg-green-500/10 text-green-400">
                      <BadgeCheck className="w-5 h-5" />
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-mono text-green-400 mb-1">validated · 94% accuracy</div>
                      <div className="text-white font-bold">Compliance report ready</div>
                    </div>
                    <div className="px-3 py-1 rounded-full bg-green-500/10 text-xs font-mono text-green-400">
                      3 sources
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Certification Program */}
      <section className="py-24 border-t border-white/5 bg-black">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row gap-12 items-center">
            <div className="w-full md:w-1/2">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-highlight/10 border border-highlight/20 mb-8">
                <Award className="w-5 h-5 text-highlight" />
                <span className="text-sm font-bold text-highlight uppercase tracking-wider">
                  Workflow Architect Certification
                </span>
              </div>
              <h2 className="text-4xl md:text-5xl font-bold text-white mb-6 leading-tight">
                Become a certified<br />
                <span className="text-highlight">Vandal Workflow Architect.</span>
              </h2>
              <p className="text-xl text-gray-400 leading-relaxed mb-8">
                11 modules, 1,600 XP, and hands-on exercises that take you from AI literacy to governance. Learn how agentic chat, validated workflows, and institutional knowledge combine into a discipline — not a gadget.
              </p>
              <ul className="space-y-3 mb-8">
                {[
                  'Free for all research administrators',
                  'Works inside Vandalizer — exercises run on real documents',
                  'Earn the Certified badge visible on every workflow you publish',
                ].map((text) => (
                  <li key={text} className="flex items-center gap-3 text-lg text-gray-300">
                    <CheckCircle className="w-5 h-5 text-highlight shrink-0" />
                    <span>{text}</span>
                  </li>
                ))}
              </ul>
              <div className="text-sm text-gray-500">
                Sign in and open the Certification panel from the top nav to begin.
              </div>
            </div>

            <div className="w-full md:w-1/2">
              <div className="glass-panel p-6 rounded-2xl border border-white/10">
                <div className="flex items-center justify-between mb-5">
                  <div className="text-sm font-mono text-gray-500">Journey Map · 3 of 11</div>
                  <div className="flex items-center gap-2 text-sm text-highlight font-bold">
                    <Sparkles className="w-4 h-4" /> 250 / 1600 XP
                  </div>
                </div>
                <div className="space-y-2.5">
                  {[
                    { n: 1, title: 'AI Literacy', xp: 50, status: 'done' },
                    { n: 2, title: 'Foundations', xp: 100, status: 'done' },
                    { n: 3, title: 'Process Mapping', xp: 100, status: 'done' },
                    { n: 4, title: 'Workflow Design', xp: 100, status: 'active' },
                    { n: 5, title: 'Extraction Engine', xp: 150, status: 'locked' },
                    { n: 6, title: 'Multi-Step Workflows', xp: 150, status: 'locked' },
                  ].map((m) => (
                    <div
                      key={m.n}
                      className={`flex items-center gap-3 p-3 rounded-lg border ${
                        m.status === 'active'
                          ? 'bg-highlight/5 border-highlight/30'
                          : m.status === 'done'
                            ? 'bg-green-500/5 border-green-500/20'
                            : 'bg-white/5 border-white/5'
                      }`}
                    >
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                        m.status === 'done'
                          ? 'bg-green-500/20 text-green-400'
                          : m.status === 'active'
                            ? 'bg-highlight/20 text-highlight'
                            : 'bg-white/10 text-gray-500'
                      }`}>
                        {m.status === 'done' ? <Check className="w-4 h-4" /> : m.n}
                      </div>
                      <div className="flex-1 text-sm text-white font-semibold">{m.title}</div>
                      <div className="text-xs font-mono text-gray-500">{m.xp} XP</div>
                    </div>
                  ))}
                  <div className="text-xs text-gray-500 font-mono pt-2 text-center">
                    + 5 more modules through Governance
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Origins */}
      <section className="py-32 relative border-t border-white/5 bg-black">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="inline-flex items-center justify-center p-3 mb-8 rounded-full bg-white/5 border border-white/10">
            <GraduationCap className="w-6 h-6 text-gray-400" />
          </div>

          <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
            Born at the University of Idaho
          </h2>
          <p className="text-gray-400 max-w-2xl mx-auto text-lg leading-relaxed mb-12">
            Vandalizer is an open-source initiative developed by the{' '}
            <strong>Artificial Intelligence for Research Administration (AI4RA)</strong> team at the
            University of Idaho.
            <br />
            <br />
            This project is made possible through the support of the{' '}
            <strong>NSF GRANTED</strong> program (Award #2427549), dedicated to reducing barriers to
            research administration and building capacity for research administration operations of
            all structures and sizes. Developed in collaboration with{' '}
            <strong>Southern Utah University</strong>.
          </p>

          <div className="flex flex-wrap justify-center gap-8 opacity-70 hover:opacity-100 transition-opacity duration-300">
            <div className="h-20 px-8 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center hover:bg-white/10 transition-colors">
              <span className="text-2xl font-bold text-highlight tracking-wider">
                University of Idaho
              </span>
            </div>
            <div className="h-20 px-8 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center hover:bg-white/10 transition-colors">
              <span className="text-2xl font-bold text-blue-400 tracking-wider">NSF GRANTED</span>
            </div>
            <div className="h-20 px-8 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center hover:bg-white/10 transition-colors">
              <span className="text-2xl font-bold text-green-400 tracking-wider">
                Southern Utah University
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Request a Demo */}
      <section className="py-24 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a0a] to-highlight/5 pointer-events-none" />
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10 text-center">
          <h2 className="text-4xl font-bold text-white mb-6">See Vandalizer in action</h2>
          <p className="text-gray-300 text-lg mb-10 max-w-2xl mx-auto">
            Research administrators, PIs, and institutions: request a live walkthrough tailored to your office&apos;s workflows. We&apos;ll show you the agentic chat, quality scoring, and workflow library on your real documents.
          </p>
          <DemoRequestForm />
          <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center items-center text-sm text-gray-500">
            <a
              href="https://github.com/ui-insight/vandalizer"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-gray-400 hover:text-highlight transition-colors"
            >
              <ExternalLink className="w-4 h-4" /> Open source on GitHub
            </a>
            <span className="hidden sm:inline text-gray-700">·</span>
            <Link to="/docs" className="text-gray-400 hover:text-highlight transition-colors">
              Read the docs
            </Link>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}
