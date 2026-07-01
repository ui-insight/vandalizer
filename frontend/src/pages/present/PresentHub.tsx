import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { Presentation, BookOpen, Copy, Check, ArrowRight } from 'lucide-react'
import { useToast } from '../../contexts/ToastContext'
import { TRACK_ORDER, TRACKS, type AudienceId } from './content'

function PitchQuickCopy({ audience }: { audience: AudienceId }) {
  const track = TRACKS[audience]
  const { toast } = useToast()
  const [copied, setCopied] = useState<null | 'spoken' | 'written'>(null)

  const copy = async (kind: 'spoken' | 'written') => {
    try {
      await navigator.clipboard.writeText(track.pitch[kind])
      setCopied(kind)
      setTimeout(() => setCopied(null), 2000)
      toast(`${track.label} ${kind} pitch copied.`, 'success')
    } catch {
      toast('Could not copy to clipboard.', 'error')
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3">
      <span className="text-sm font-medium text-gray-200">{track.label}</span>
      <div className="flex items-center gap-2">
        {(['spoken', 'written'] as const).map((kind) => (
          <button
            key={kind}
            onClick={() => copy(kind)}
            className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/10 hover:text-white transition-colors"
          >
            {copied === kind ? (
              <Check className="w-3.5 h-3.5 text-green-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
            {kind === 'spoken' ? 'Spoken' : 'Written'}
          </button>
        ))}
      </div>
    </div>
  )
}

export function PresentHub() {
  return (
    <div id="main-content" tabIndex={-1} className="space-y-12">
      {/* Hero */}
      <header>
        <h1 className="text-4xl sm:text-5xl font-bold text-white tracking-tight">
          Present &amp; Pitch
        </h1>
        <p className="mt-4 text-lg text-gray-400 max-w-2xl leading-relaxed">
          Ready-to-use material for introducing Vandalizer — pick your audience, then
          read it, present it live, or copy an elevator pitch. Everything here is public:
          share any link, no account needed.
        </p>
      </header>

      {/* Audience cards */}
      <section>
        <h2 className="text-sm font-bold uppercase tracking-wider text-[#f1b300] mb-4">
          Choose your audience
        </h2>
        <div className="grid gap-5 sm:grid-cols-2">
          {TRACK_ORDER.map((id) => {
            const track = TRACKS[id]
            const Icon = track.icon
            return (
              <div
                key={id}
                className="flex flex-col rounded-xl border border-white/10 bg-white/[0.03] p-6 hover:border-[#f1b300]/30 transition-colors"
              >
                <div className="flex items-center gap-3 mb-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#f1b300]/10 text-[#f1b300]">
                    <Icon className="w-5 h-5" />
                  </span>
                  <div>
                    <h3 className="text-lg font-bold text-white">{track.label}</h3>
                    <p className="text-sm text-gray-500">{track.tagline}</p>
                  </div>
                </div>
                <ul className="flex-1 space-y-1.5 mb-5">
                  {track.valueProps.slice(0, 3).map((vp) => (
                    <li key={vp} className="flex items-start gap-2 text-sm text-gray-300">
                      <span className="text-[#f1b300] mt-1 leading-none">&#x2022;</span>
                      <span>{vp}</span>
                    </li>
                  ))}
                </ul>
                <div className="flex items-center gap-2">
                  <Link
                    to="/docs/present/$audience"
                    params={{ audience: id }}
                    search={{ mode: undefined, slide: undefined, pitch: undefined }}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-[#f1b300] px-3.5 py-2 text-sm font-bold text-black hover:bg-[#d49e00] transition-colors"
                  >
                    <BookOpen className="w-4 h-4" />
                    Read
                  </Link>
                  <Link
                    to="/docs/present/$audience"
                    params={{ audience: id }}
                    search={{ mode: 'deck', slide: undefined, pitch: undefined }}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-3.5 py-2 text-sm font-medium text-gray-200 hover:bg-white/10 transition-colors"
                  >
                    <Presentation className="w-4 h-4" />
                    Present
                  </Link>
                  <ArrowRight className="w-4 h-4 text-gray-600 ml-auto" />
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Quick-copy pitch strip */}
      <section>
        <h2 className="text-sm font-bold uppercase tracking-wider text-[#f1b300] mb-1">
          Grab a pitch in 10 seconds
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          Copy a ready-made spoken or written pitch for any audience.
        </p>
        <div className="space-y-2.5">
          {TRACK_ORDER.map((id) => (
            <PitchQuickCopy key={id} audience={id} />
          ))}
        </div>
      </section>
    </div>
  )
}
