import { useState } from 'react'
import { Share2, ShieldCheck } from 'lucide-react'
import { useToast } from '../../contexts/ToastContext'
import { useShareLabel } from '../../lib/catalogLabels'
import { VerificationSubmitModal } from './VerificationSubmitModal'

/** Scores at or above this get the "Great results" framing; any score can share. */
const HIGH_SCORE = 80

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

  const high = score !== null && score >= HIGH_SCORE
  const rounded = score === null ? null : Math.round(score)
  const accent = high ? '#059669' : '#374151'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '12px 16px', borderRadius: 8,
      backgroundColor: high ? '#ecfdf5' : '#f9fafb',
      border: `1px solid ${high ? '#a7f3d0' : '#e5e7eb'}`,
    }}>
      {high
        ? <ShieldCheck aria-hidden="true" style={{ width: 20, height: 20, color: accent, flexShrink: 0 }} />
        : <Share2 aria-hidden="true" style={{ width: 20, height: 20, color: '#6b7280', flexShrink: 0 }} />}
      <div style={{ flex: 1, fontSize: 13, color: high ? '#065f46' : '#374151' }}>
        {high ? (
          <><strong>Great results!</strong> This {kindNoun} scored {rounded}%. Share it so colleagues can use it too.</>
        ) : (
          <>
            {rounded !== null && <>This {kindNoun} scored {rounded}%. </>}
            You can share it at any score. An examiner looks it over, or you can ask one for a second pair of eyes.
          </>
        )}
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
            borderRadius: 6, border: `1px solid ${high ? '#a7f3d0' : '#d1d5db'}`, backgroundColor: '#fff',
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
