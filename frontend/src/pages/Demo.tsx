import { useState, type FormEvent } from 'react'
import { Link } from '@tanstack/react-router'
import {
  ArrowLeft,
  ArrowRight,
  Loader2,
  Mail,
  ExternalLink,
  Coins,
  Infinity as InfinityIcon,
  ShieldCheck,
} from 'lucide-react'
import { Footer } from '../components/layout/Footer'
import { resendCredentials } from '../api/demo'

// ---------------------------------------------------------------------------
// What the trial is, and how to start it.
//
// This page used to be the front door: a 26-question research survey ending in
// a waitlist position. Both are gone — accounts are token-metered, so
// activation is immediate and there is no queue to hold anyone in. The survey
// still exists, but as the price of a top-up, asked once someone has actually
// used the product and has something to say.
// ---------------------------------------------------------------------------

function ResendLink() {
  const [uuid, setUuid] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function handleResend(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMessage('')
    setError('')
    try {
      const res = await resendCredentials(uuid.trim())
      if (res.ok) setMessage(res.message)
      else setError(res.message)
    } catch {
      setError("We couldn't find a trial for that ID.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-10 p-6 rounded-xl border border-white/10 bg-white/5 text-left">
      <h2 className="text-lg font-bold text-white mb-2">Lost your sign-in link?</h2>
      <p className="text-sm text-gray-400 mb-4">
        If an admin set your account up for you, paste the trial ID from that
        email and we'll send a fresh one-click link.
      </p>
      <form onSubmit={handleResend} className="flex gap-3">
        <input
          type="text"
          aria-label="Trial ID"
          placeholder="Trial ID"
          value={uuid}
          onChange={(e) => setUuid(e.target.value)}
          className="flex-1 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
        />
        <button
          type="submit"
          disabled={busy || !uuid.trim()}
          className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-6 py-3 font-bold text-white hover:bg-white/20 disabled:opacity-50 transition-colors"
        >
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Mail className="w-5 h-5" />}
          Send
        </button>
      </form>
      {message && <p className="mt-3 text-sm text-green-400">{message}</p>}
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
    </div>
  )
}

const INCLUDED = [
  {
    icon: Coins,
    title: '2 million AI tokens, included',
    body: 'Enough to put real documents through real extractions — not a sampler.',
  },
  {
    icon: InfinityIcon,
    title: 'No time limit',
    body: 'Nothing expires on a date. Work at whatever pace your cycle allows, and top up for free when you run out.',
  },
  {
    icon: ShieldCheck,
    title: 'The whole platform',
    body: 'Extraction workflows, knowledge bases, agentic chat with cited sources, and the validation stack.',
  },
]

export default function Demo() {
  return (
    <div className="bg-[#0a0a0a] text-gray-200 antialiased min-h-screen">
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link
            to="/landing"
            search={{ error: undefined, invite_token: undefined, admin: undefined, next: undefined, register: undefined }}
            className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="text-xl font-bold text-white">Vandalizer</span>
          </Link>
          <a
            href="https://github.com/ui-insight/vandalizer"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-[#f1b300] transition-colors"
          >
            <ExternalLink className="w-4 h-4" />
            GitHub
          </a>
        </div>
      </nav>

      <div className="relative z-10 pt-28 pb-16">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h1 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Try Vandalizer on your own documents
          </h1>
          <p className="text-gray-400 mb-10">
            Create an account and you're in — no queue, no sales call. Confirm
            your email and the AI features switch on.
          </p>

          <div className="grid gap-4 text-left mb-10">
            {INCLUDED.map(({ icon: Icon, title, body }) => (
              <div
                key={title}
                className="flex gap-4 p-5 rounded-xl border border-white/10 bg-white/5"
              >
                <Icon className="w-5 h-5 shrink-0 text-[#f1b300] mt-0.5" aria-hidden="true" />
                <div>
                  <div className="font-bold text-white">{title}</div>
                  <p className="text-sm text-gray-400 mt-1">{body}</p>
                </div>
              </div>
            ))}
          </div>

          <Link
            to="/landing"
            search={{ error: undefined, invite_token: undefined, admin: undefined, next: undefined, register: '1' }}
            className="inline-flex items-center gap-2 rounded-lg bg-[#f1b300] px-8 py-4 text-lg font-bold text-black hover:bg-[#d49e00] transition-colors"
          >
            Create your account <ArrowRight className="w-5 h-5" />
          </Link>

          <ResendLink />
        </div>
      </div>

      <Footer />
    </div>
  )
}
