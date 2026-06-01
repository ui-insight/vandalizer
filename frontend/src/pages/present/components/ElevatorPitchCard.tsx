import { useState } from 'react'
import { Copy, Check, Mic, Mail } from 'lucide-react'
import { useToast } from '../../../contexts/ToastContext'
import type { ElevatorPitch } from '../content'
import { cn } from '../../../lib/cn'

interface ElevatorPitchCardProps {
  pitch: ElevatorPitch
  /** Optionally emphasize one variant (from ?pitch=spoken|written). */
  highlight?: 'spoken' | 'written'
}

function CopyablePitch({
  icon: Icon,
  kind,
  caption,
  text,
  highlighted,
}: {
  icon: typeof Mic
  kind: string
  caption: string
  text: string
  highlighted?: boolean
}) {
  const { toast } = useToast()
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      toast(`${kind} pitch copied — paste it anywhere.`, 'success')
    } catch {
      toast('Could not copy to clipboard.', 'error')
    }
  }

  return (
    <div
      className={cn(
        'rounded-xl border p-5 sm:p-6 transition-colors',
        highlighted
          ? 'border-[#f1b300]/40 bg-[#f1b300]/[0.07]'
          : 'border-white/10 bg-white/[0.03]',
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <Icon className="w-4 h-4 text-[#f1b300]" />
          {kind}
          <span className="font-normal text-gray-500">· {caption}</span>
        </div>
        <button
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-white/10 hover:text-white transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-green-400" /> Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" /> Copy
            </>
          )}
        </button>
      </div>
      <p className="text-gray-200 leading-relaxed">{text}</p>
    </div>
  )
}

/** Two copy-ready elevator pitches: a spoken (~30s) and a written paragraph. */
export function ElevatorPitchCard({ pitch, highlight }: ElevatorPitchCardProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <CopyablePitch
        icon={Mic}
        kind="Spoken"
        caption="~30 seconds, read aloud"
        text={pitch.spoken}
        highlighted={highlight === 'spoken'}
      />
      <CopyablePitch
        icon={Mail}
        kind="Written"
        caption="one paragraph, for email"
        text={pitch.written}
        highlighted={highlight === 'written'}
      />
    </div>
  )
}
