import { useEffect, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { Sparkles, X } from 'lucide-react'

interface Props {
  onConfirm: (coverage: 'quick' | 'standard' | 'exhaustive') => void
  onClose: () => void
}

const OPTIONS: { id: 'quick' | 'standard' | 'exhaustive'; label: string; count: number; cost: string }[] = [
  { id: 'quick', label: 'Quick', count: 5, cost: '~10 LLM calls' },
  { id: 'standard', label: 'Standard', count: 10, cost: '~20 LLM calls' },
  { id: 'exhaustive', label: 'Exhaustive', count: 25, cost: '~50 LLM calls' },
]

export function GenerateTestQueriesModal({ onConfirm, onClose }: Props) {
  const [choice, setChoice] = useState<'quick' | 'standard' | 'exhaustive'>('standard')

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Auto-generate test queries"
        style={{
          width: 440, padding: 20, backgroundColor: '#1f1f1f',
          border: '1px solid #2e2e2e', borderRadius: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Sparkles size={16} style={{ color: '#7c3aed' }} aria-hidden="true" />
          <h3 style={{ margin: 0, fontSize: 15, color: '#fff' }}>Auto-generate test queries</h3>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ marginLeft: 'auto', background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: '#888' }}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        <div style={{ fontSize: 12, color: '#aaa', marginBottom: 14 }}>
          The LLM will sample chunks from your KB and propose questions whose answers
          require retrieval — useful for measuring how much your KB lifts answer
          quality vs. a no-KB baseline.
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
          {OPTIONS.map(opt => {
            const active = choice === opt.id
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setChoice(opt.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 12px', textAlign: 'left',
                  backgroundColor: active ? 'rgba(124, 58, 237, 0.12)' : '#262626',
                  border: '1px solid ' + (active ? '#7c3aed' : '#333'),
                  borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', color: '#e5e5e5',
                }}
              >
                <span style={{
                  width: 14, height: 14, borderRadius: '50%',
                  border: '2px solid ' + (active ? '#7c3aed' : '#555'),
                  backgroundColor: active ? '#7c3aed' : 'transparent',
                  flexShrink: 0,
                }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{opt.label}</div>
                  <div style={{ fontSize: 11, color: '#888' }}>up to {opt.count} questions</div>
                </div>
                <div style={{ fontSize: 11, color: '#666' }}>{opt.cost}</div>
              </button>
            )
          })}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" onClick={onClose} style={{
            padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            color: '#aaa', background: 'transparent', border: '1px solid #333',
            borderRadius: 6, cursor: 'pointer',
          }}>
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(choice)}
            style={{
              padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
              color: '#fff', backgroundColor: '#7c3aed',
              border: '1px solid #7c3aed', borderRadius: 6, cursor: 'pointer',
            }}
          >
            Generate
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
