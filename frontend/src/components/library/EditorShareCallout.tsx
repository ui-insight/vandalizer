import { useState } from 'react'
import { Share2 } from 'lucide-react'
import { useToast } from '../../contexts/ToastContext'
import { useShareLabel } from '../../lib/catalogLabels'
import { VerificationSubmitModal } from './VerificationSubmitModal'

/**
 * The editor's way into the share wizard — the same one Library → ⋯ → Share
 * with everyone opens. Shown at any score: the server accepts any score, and a
 * low-scoring item is the one most worth a second pair of eyes. Hidden once
 * the item is verified, as in the Library menu.
 */
export function EditorShareCallout({
  itemKind,
  itemId,
  itemTitle,
  kindNoun,
  score,
  verified,
}: {
  itemKind: 'workflow' | 'search_set'
  itemId: string
  itemTitle?: string
  /** "workflow" or "extraction", for the sentence. */
  kindNoun: string
  /** Latest quality score (0–100), or null when it has none yet. */
  score: number | null
  verified?: boolean
}) {
  const { toast } = useToast()
  const shareLabel = useShareLabel()
  const [open, setOpen] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  if (verified) return null

  const accent = '#374151'

  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12,
      padding: '12px 16px', borderRadius: 8,
      backgroundColor: '#f9fafb',
      border: '1px solid #e5e7eb',
    }}>
      <Share2 aria-hidden="true" style={{ width: 20, height: 20, color: '#6b7280', flexShrink: 0 }} />
      <div style={{ flex: '1 1 160px', minWidth: 0, fontSize: 13, color: accent }}>
        <strong>Share this {kindNoun} for review.</strong>{' '}
        {score != null
          ? 'Your evaluation results travel with it, so colleagues can review the evidence and help improve it.'
          : 'Not evaluated yet? An examiner can test it for you.'}
      </div>
      {submitted ? (
        <span style={{ fontSize: 12, fontWeight: 600, color: accent, whiteSpace: 'nowrap' }}>Sent to the examiners</span>
      ) : (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setOpen(true) }}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            borderRadius: 6, border: '1px solid #d1d5db', backgroundColor: '#fff',
            color: accent, cursor: 'pointer', whiteSpace: 'nowrap',
          }}
        >
          {shareLabel}
        </button>
      )}
      {open && (
        <VerificationSubmitModal
          itemKind={itemKind}
          itemId={itemId}
          itemTitle={itemTitle}
          onClose={() => setOpen(false)}
          onSubmitted={() => {
            setSubmitted(true)
            toast('Sent to the examiners — you\'ll hear back when someone has looked', 'success')
          }}
        />
      )}
    </div>
  )
}
