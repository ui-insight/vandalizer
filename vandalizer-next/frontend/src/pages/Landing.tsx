import { useState, useEffect, type FormEvent } from 'react'
import { Navigate, useSearch } from '@tanstack/react-router'
import { useAuth } from '../hooks/useAuth'
import { getAuthConfig, type AuthConfig } from '../api/auth'
import {
  FileText,
  Cpu,
  Table,
  Check,
  ShieldCheck,
  ScanText,
  FileEdit,
  Loader2,
  GitMerge,
  CheckCircle,
  Users,
  Lock,
  RefreshCw,
  User,
  ArrowDown,
  FileInput,
  ScanLine,
  PenTool,
  GraduationCap,
  Mail,
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
        placeholder="Username or Email"
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
        {submitting ? 'Signing in...' : 'SIGN IN'}
      </button>
    </form>
  )
}

function LandingRegisterForm({ onSwitch }: { onSwitch: () => void }) {
  const { register } = useAuth()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      // user_id = email, matching Flask behavior
      await register(email, email, password, name || undefined)
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
        className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
      />
      <input
        type="email"
        placeholder="Email Address"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
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
        {submitting ? 'Creating account...' : 'CREATE ACCOUNT'}
      </button>
      <p className="text-center text-sm text-gray-400">
        Already have an account?{' '}
        <button type="button" onClick={onSwitch} className="font-bold text-white hover:text-[#f1b300]">
          Sign in
        </button>
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

  if (!config) {
    return (
      <div className="flex justify-center py-8">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-[#f1b300] border-t-transparent" />
      </div>
    )
  }

  const oauthEnabled = config.auth_methods.includes('oauth')
  const passwordEnabled = config.auth_methods.includes('password')
  const azureProvider = config.oauth_providers.find(
    (p) => p.provider === 'azure' && p.configured,
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
                  className="font-bold text-white hover:text-[#f1b300]"
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

      {!oauthEnabled && !passwordEnabled && (
        <p className="text-sm text-gray-400">
          No authentication methods are enabled. Please contact an administrator.
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Landing page
// ---------------------------------------------------------------------------

export default function Landing() {
  const { user, loading } = useAuth()
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)

  useEffect(() => {
    getAuthConfig().then(setAuthConfig)
  }, [])

  if (loading) return null
  if (user) return <Navigate to="/" />

  return (
    <div className="landing-page bg-[#0a0a0a] text-gray-200 antialiased w-full min-h-screen relative">
      {/* Background Ambient Glow */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-yellow-600/10 rounded-full blur-[120px] animate-pulse" />
        <div
          className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-gray-800/30 rounded-full blur-[120px] animate-pulse"
          style={{ animationDelay: '2s' }}
        />
      </div>

      {/* Hero */}
      <div className="relative z-10 pt-16 pb-8 border-t border-white/5">
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
            <g className="tech-wave">
              <use xlinkHref="#tech-line" x="48" y="0" fill="none" stroke="#f1b300" strokeWidth="0.3" />
              <use xlinkHref="#tech-line" x="48" y="3" fill="none" stroke="#f1b300" strokeWidth="0.5" />
              <use xlinkHref="#tech-line" x="48" y="5" fill="none" stroke="#f1b300" strokeWidth="0.2" />
              <use xlinkHref="#tech-line" x="48" y="7" fill="none" stroke="#f1b300" strokeWidth="0.1" />
              <use xlinkHref="#tech-line" x="48" y="12" fill="none" stroke="#f1b300" strokeWidth="0.4" />
              <use xlinkHref="#tech-line" x="48" y="20" fill="none" stroke="#f1b300" strokeWidth="0.15" />
            </g>
          </svg>
        </div>

        <div className="relative z-10 flex flex-col items-center text-center px-4">
          {/* Early Access Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#f1b300]/10 border border-[#f1b300]/20 mb-10 hover:bg-[#f1b300]/20 transition-colors cursor-default">
            <span className="flex h-2 w-2 rounded-full bg-[#f1b300] animate-pulse" />
            <span className="text-sm font-bold text-[#f1b300] tracking-wide uppercase">
              Now in Limited Early Access
            </span>
          </div>

          {/* Logo */}
          <img
            src="/images/Vandalizer_Wordmark_Color_RGB+W.png"
            alt="Vandalizer"
            className="w-full max-w-[500px] mb-5"
          />

          {/* Tagline */}
          <p className="text-xl md:text-2xl text-gray-300 max-w-2xl mx-auto leading-relaxed mb-8">
            Next generation document handling, built at the University of Idaho.
          </p>

          {/* Auth Block */}
          <AuthBlock config={authConfig} />
        </div>
      </div>

      {/* Hero Visualization */}
      <main className="relative z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="mt-24 relative mx-auto max-w-5xl hidden md:block" style={{ animation: 'float 6s ease-in-out infinite' }}>
            <div className="absolute -inset-1 bg-gradient-to-r from-[#d49e00] to-yellow-600 rounded-xl blur opacity-20" />
            <div className="relative glass-panel rounded-xl border border-white/10 overflow-hidden shadow-2xl">
              {/* Window chrome */}
              <div className="flex items-center px-4 py-3 border-b border-white/5 bg-black/40">
                <div className="flex space-x-2">
                  <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/50" />
                  <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/50" />
                  <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/50" />
                </div>
                <div className="ml-4 text-xs text-gray-500 font-mono">workflow_pipeline.json</div>
              </div>
              {/* Pipeline columns */}
              <div className="p-8 grid grid-cols-3 gap-6 text-left">
                {/* Input */}
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-xl font-semibold text-gray-400 uppercase tracking-wider">
                    <FileText className="w-4 h-4 text-[#f1b300]" /> Input
                  </div>
                  <div className="bg-[#262626] p-4 rounded-lg border border-white/5 font-mono text-xs text-gray-400 leading-relaxed">
                    <span className="text-gray-500"># NIH_Grant_Announcement.pdf</span>
                    <br />
                    <span className="text-white">Due Date:</span> Oct 05, 2025
                    <br />
                    <span className="text-white">Budget Cap:</span> $250,000
                  </div>
                </div>
                {/* Processing */}
                <div className="space-y-3 relative">
                  <div className="flex items-center gap-2 text-xl font-semibold text-gray-400 uppercase tracking-wider">
                    <Cpu className="w-4 h-4 text-cyan-400" /> Processing
                  </div>
                  <div className="bg-[#262626] p-4 rounded-lg border border-cyan-500/20 font-mono text-xs relative overflow-hidden h-full">
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-[#f1b300] to-transparent" style={{ animation: 'landing-shimmer 2s infinite' }} />
                    <div className="space-y-2 pt-1">
                      <div className="flex justify-between">
                        <span className="text-[#f1b300]">Extracting...</span>
                        <Check className="w-3 h-3 text-green-500" />
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[#f1b300]">Verifying...</span>
                        <ShieldCheck className="w-3 h-3 text-green-500" />
                      </div>
                    </div>
                  </div>
                </div>
                {/* Output */}
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-xl font-semibold text-gray-400 uppercase tracking-wider">
                    <Table className="w-4 h-4 text-green-400" /> Output
                  </div>
                  <div className="bg-[#262626] p-4 rounded-lg border border-white/5 font-mono text-xs text-green-300">
                    {'{\n'}
                    {'  "deadline": "2025-10-05",\n'}
                    {'  "budget": 250000\n'}
                    {'}'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        {/* Grid Background Effect */}
        <div className="absolute inset-0 grid-bg -z-10 opacity-20" />
      </main>

      {/* Tasks & Extractions */}
      <section className="py-32 relative border-t border-white/5 bg-[#171717]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col lg:flex-row gap-16 items-center">
            <div className="w-full lg:w-1/2">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#f1b300]/10 border border-[#f1b300]/20 mb-8">
                <CheckCircle className="w-5 h-5 text-[#f1b300]" />
                <span className="text-sm font-bold text-[#f1b300] uppercase tracking-wider">
                  Atomic Units of Work
                </span>
              </div>
              <h2 className="text-4xl md:text-5xl font-bold text-white mb-8 leading-tight">
                Verified <span className="text-[#f1b300]">Tasks</span> &{' '}
                <br />
                Reliable <span className="text-[#f1b300]">Extractions</span>
              </h2>
              <p className="text-xl text-gray-400 leading-relaxed mb-8">
                Forget generic &ldquo;chat with PDF&rdquo;. Vandalizer uses specialized tasks to
                perform specific actions with high accuracy.
              </p>
              <div className="space-y-6">
                <div className="flex gap-4">
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10 h-fit">
                    <ScanText className="w-6 h-6 text-[#f1b300]" />
                  </div>
                  <div>
                    <h4 className="text-xl font-bold text-white mb-2">Structured Extraction</h4>
                    <p className="text-lg text-gray-400">
                      Pull dates, budgets, and requirements from messy PDFs into clean JSON.
                    </p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10 h-fit">
                    <FileEdit className="w-6 h-6 text-[#f1b300]" />
                  </div>
                  <div>
                    <h4 className="text-xl font-bold text-white mb-2">Smart Summarization</h4>
                    <p className="text-lg text-gray-400">
                      Generate executive summaries tailored to specific grant guidelines.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Task cards visual */}
            <div className="w-full lg:w-1/2">
              <div className="relative">
                <div className="glass-panel p-6 rounded-xl border border-white/10 mb-4 transform translate-x-4">
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-sm font-mono text-gray-500">Extraction Task</span>
                    <span className="px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs font-bold">
                      COMPLETED
                    </span>
                  </div>
                  <div className="space-y-2 font-mono text-sm">
                    <div className="text-gray-400">&quot;action&quot;: &quot;extract_deadline&quot;</div>
                    <div className="text-[#f1b300]">&quot;result&quot;: &quot;extraction.csv&quot;</div>
                  </div>
                </div>
                <div className="glass-panel p-6 rounded-xl border border-white/10 mb-4 transform -translate-x-4 z-10 relative bg-[#262626]">
                  <div className="flex justify-between items-center mb-4">
                    <span className="text-sm font-mono text-gray-500">Verified Prompt</span>
                    <span className="px-2 py-1 rounded bg-blue-500/20 text-blue-400 text-xs font-bold">
                      PROCESSING
                    </span>
                  </div>
                  <div className="space-y-2 font-mono text-sm">
                    <div className="text-gray-400">&quot;action&quot;: &quot;check_compliance&quot;</div>
                    <div className="flex items-center gap-2 text-blue-400">
                      <Loader2 className="w-4 h-4 animate-spin" /> Analyzing...
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
                  End-to-End Automation
                </span>
              </div>
              <h2 className="text-4xl md:text-5xl font-bold text-white mb-8 leading-tight">
                Chain Tasks into <br />
                <span className="text-blue-400">Powerful Workflows</span>
              </h2>
              <p className="text-xl text-gray-400 leading-relaxed mb-8">
                Combine tasks to handle complex processes. Output from one task becomes input for
                the next, creating reliable pipelines that scale.
              </p>
              <ul className="space-y-4">
                {[
                  'Standardize processes across your team',
                  'Handle conditional logic and branching',
                  'Reproducible results, every time',
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

                  <div className="w-full p-4 rounded-lg bg-[#262626] border border-[#f1b300]/30 flex items-center justify-between shadow-[0_0_15px_rgba(241,179,0,0.1)]">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded bg-[#f1b300]/10">
                        <ScanLine className="w-5 h-5 text-[#f1b300]" />
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
          <div className="mb-20">
            <h2 className="text-4xl font-bold text-white mb-6">Tools to Augment your Team</h2>
            <p className="text-xl text-gray-400 max-w-2xl mx-auto">
              Collaborate, Verify, and Scale with confidence using our secure platform.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Feature 1: Collaborative Workspace (large) */}
            <div className="col-span-1 md:col-span-2 glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-[#f1b300]/10 text-[#f1b300]">
                  <Users className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">01</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-[#f1b300] transition-colors relative z-10">
                Unified Team Workspace
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed mb-6 relative z-10 max-w-lg">
                All your team&apos;s files and workflows in one central hub. Share specific tasks or
                entire pipelines instantly. No more emailing refined prompts or Python scripts back
                and forth.
              </p>
              <div className="absolute -bottom-6 -right-6 w-40 h-40 bg-[#f1b300]/5 rounded-full blur-2xl group-hover:bg-[#f1b300]/10 transition-colors" />
            </div>

            {/* Feature 2: Private & Secure */}
            <div className="glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-gray-700/30 text-gray-300">
                  <Lock className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">02</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-gray-300 transition-colors relative z-10">
                Private & Secure
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed relative z-10">
                Powerful AI models that are private and secure. Your data stays within your control
                and is never used to train public models.
              </p>
            </div>

            {/* Feature 3: Reproducible */}
            <div className="glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-gray-700/30 text-gray-300">
                  <RefreshCw className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">03</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-gray-300 transition-colors relative z-10">
                Reproducible
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed relative z-10">
                Eliminate variability. Build workflows that produce consistent, standardized outputs
                every time, regardless of who runs them.
              </p>
            </div>

            {/* Feature 4: Evaluate Once (large) */}
            <div className="col-span-1 md:col-span-2 glass-panel rounded-2xl p-8 hover:bg-white/5 transition-colors group border border-white/5 relative overflow-hidden">
              <div className="flex items-start justify-between mb-6 relative z-10">
                <div className="p-3 rounded-lg bg-[#f1b300]/10 text-[#f1b300]">
                  <CheckCircle className="w-8 h-8" />
                </div>
                <span className="text-sm font-mono text-gray-500">04</span>
              </div>
              <h3 className="text-2xl font-bold text-white mb-4 group-hover:text-[#f1b300] transition-colors relative z-10">
                Evaluate Once, Run Everywhere
              </h3>
              <p className="text-gray-400 text-xl leading-relaxed mb-6 relative z-10 max-w-lg">
                Create a &ldquo;Golden Set&rdquo; of documents to verify a workflow&apos;s accuracy. Once a
                workflow passes evaluation, deploy it to your entire team with the confidence that it
                performs correctly.
              </p>
              <div className="absolute -bottom-6 -right-6 w-40 h-40 bg-[#f1b300]/5 rounded-full blur-2xl group-hover:bg-[#f1b300]/10 transition-colors" />
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
                Not a replacement.
                <br />
                An augmentation.
              </h2>
              <div className="space-y-8">
                {[
                  {
                    n: 1,
                    title: 'Upload Document',
                    desc: 'Drag and drop RFPs, contracts, or emails into the secure workspace.',
                  },
                  {
                    n: 2,
                    title: 'Select Tasks',
                    desc: 'Choose from pre-built "Verified" workflows or create custom extraction logic.',
                  },
                  {
                    n: 3,
                    title: 'Review & Export',
                    desc: 'Validate the AI output against the source document and export to your system.',
                  },
                ].map((step) => (
                  <div key={step.n} className="flex gap-6">
                    <div className="w-10 h-10 rounded-full bg-[#f1b300]/20 flex items-center justify-center text-lg font-bold text-[#f1b300] shrink-0">
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
                <blockquote className="border-l-4 border-[#f1b300] pl-6 italic text-gray-300 text-xl leading-relaxed">
                  &ldquo;Vandalizer allows RAs to leverage their institutional knowledge to create
                  flexible workflows targeted at common issues.&rdquo;
                </blockquote>
              </div>
            </div>

            {/* How-it-works visual */}
            <div className="w-full md:w-1/2">
              <div className="glass-panel p-8 rounded-2xl border border-white/10 relative overflow-hidden">
                <div className="absolute inset-0 grid-bg opacity-30" />
                <div className="relative z-10 flex flex-col gap-8">
                  {/* Step 1: User Input */}
                  <div className="flex items-center gap-4 p-4 rounded-xl bg-[#262626] border border-white/5">
                    <div className="p-3 rounded-lg bg-white/10 text-white">
                      <User className="w-6 h-6" />
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-mono text-gray-400 mb-1">Input Source</div>
                      <div className="text-white font-bold">Research Administrator</div>
                    </div>
                    <div className="px-3 py-1 rounded-full bg-white/5 text-xs font-mono text-gray-400">
                      PDF/Email
                    </div>
                  </div>

                  <div className="flex justify-center -my-2">
                    <ArrowDown className="w-6 h-6 text-gray-600 animate-bounce" />
                  </div>

                  {/* Step 2: Core */}
                  <div className="relative p-6 rounded-xl bg-[#0a0a0a] border border-[#f1b300]/30 shadow-[0_0_30px_rgba(241,179,0,0.1)]">
                    <div className="absolute inset-0 bg-[#f1b300]/5 animate-pulse rounded-xl" />
                    <div className="relative flex items-center gap-4">
                      <div className="p-3 rounded-lg bg-[#f1b300]/10 text-[#f1b300]">
                        <Cpu className="w-8 h-8" />
                      </div>
                      <div className="flex-1">
                        <div className="text-sm font-mono text-[#f1b300] mb-1">Vandalizer Core</div>
                        <div className="text-white font-bold">AI Processing & Extraction</div>
                      </div>
                    </div>
                    <div className="mt-4 p-3 rounded bg-black/50 font-mono text-xs text-gray-400 border border-white/5">
                      <span className="text-[#f1b300]">&gt;&gt;</span> Extracting key_dates...
                      <br />
                      <span className="text-[#f1b300]">&gt;&gt;</span> Validating budget_caps...
                      <br />
                      <span className="text-green-500">&#10003;</span> Confidence: 98.5%
                    </div>
                  </div>

                  <div className="flex justify-center -my-2">
                    <ArrowDown
                      className="w-6 h-6 text-gray-600 animate-bounce"
                      style={{ animationDelay: '0.5s' }}
                    />
                  </div>

                  {/* Step 3: Expert Review */}
                  <div className="flex items-center gap-4 p-4 rounded-xl bg-[#262626] border border-green-500/20">
                    <div className="p-3 rounded-lg bg-green-500/10 text-green-400">
                      <ShieldCheck className="w-6 h-6" />
                    </div>
                    <div className="flex-1">
                      <div className="text-sm font-mono text-green-400 mb-1">Final Validation</div>
                      <div className="text-white font-bold">Human Expert Approval</div>
                    </div>
                    <div className="px-3 py-1 rounded-full bg-green-500/10 text-xs font-mono text-green-400">
                      Verified
                    </div>
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
            research administration and building capacity at emerging research institutions.
          </p>

          <div className="flex flex-wrap justify-center gap-8 opacity-70 hover:opacity-100 transition-opacity duration-300">
            <div className="h-20 px-8 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center hover:bg-white/10 transition-colors">
              <span className="text-2xl font-bold text-[#f1b300] tracking-wider">
                University of Idaho
              </span>
            </div>
            <div className="h-20 px-8 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center hover:bg-white/10 transition-colors">
              <span className="text-2xl font-bold text-blue-400 tracking-wider">NSF GRANTED</span>
            </div>
          </div>
        </div>
      </section>

      {/* Collaboration CTA */}
      <section className="py-24 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a0a] to-[#f1b300]/5 pointer-events-none" />
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10 text-center">
          <h2 className="text-4xl font-bold text-white mb-6">Help Shape the Future of RA</h2>
          <p className="text-gray-300 text-lg mb-10 max-w-2xl mx-auto">
            We are actively seeking collaborators, testers, and contributors. If you are a Research
            Administrator interested in piloting Vandalizer, or a developer wanting to contribute to
            the codebase, we want to hear from you.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="https://ai4ra.uidaho.edu/contact/"
              className="inline-flex h-14 items-center justify-center rounded-full bg-white text-black px-8 font-bold text-lg transition-all hover:bg-gray-200 hover:scale-105 shadow-[0_0_20px_rgba(255,255,255,0.2)]"
            >
              <Mail className="w-5 h-5 mr-2" /> Contact the Team
            </a>
            <a
              href="https://ai4ra.uidaho.edu"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-14 items-center justify-center rounded-full border border-white/20 bg-white/5 px-8 font-bold text-white transition-all hover:bg-white/10"
            >
              Visit AI4RA Website
            </a>
          </div>
        </div>
      </section>
    </div>
  )
}
