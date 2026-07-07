import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { Loader2 } from 'lucide-react'

interface CreateKBModalProps {
  onClose: () => void
  onCreate: (title: string, description: string) => Promise<void>
}

export function CreateKBModal({ onClose, onCreate }: CreateKBModalProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const titleRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    titleRef.current?.focus()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const canSubmit = title.trim().length > 0 && !creating

  const handleSubmit = async () => {
    if (!canSubmit) return
    setCreating(true)
    setError(null)
    try {
      await onCreate(title.trim(), description.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create knowledge base')
      setCreating(false)
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: '#1e1e1e', borderRadius: 12, padding: 24, width: 440,
          border: '1px solid #3a3a3a', maxHeight: '85vh', overflowY: 'auto',
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, color: '#fff', marginBottom: 6 }}>
          Create Knowledge Base
        </div>
        <p style={{ fontSize: 12, color: '#888', margin: '0 0 16px', lineHeight: 1.5 }}>
          A knowledge base groups documents and URLs so you can chat with them as one
          searchable corpus. A clear title and short description help your team (and
          future-you) understand what it covers.
        </p>

        <label htmlFor="create-kb-title" style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#aaa', marginBottom: 4 }}>
          Title
        </label>
        <input
          id="create-kb-title"
          ref={titleRef}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && canSubmit) handleSubmit() }}
          placeholder="e.g. NIH Grant Proposals 2026"
          aria-invalid={!!error}
          aria-describedby={error ? 'create-kb-error' : undefined}
          style={{
            width: '100%', padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
            backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
            color: '#e5e5e5', marginBottom: 14, boxSizing: 'border-box',
          }}
        />

        <label htmlFor="create-kb-description" style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#aaa', marginBottom: 4 }}>
          Description
        </label>
        <textarea
          id="create-kb-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What is in this knowledge base, and what should it be used for?"
          rows={4}
          style={{
            width: '100%', padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
            backgroundColor: '#2a2a2a', border: '1px solid #3a3a3a', borderRadius: 6,
            color: '#e5e5e5', marginBottom: 6, resize: 'vertical',
            boxSizing: 'border-box', lineHeight: 1.5,
          }}
        />
        <p style={{ fontSize: 11, color: '#666', margin: '0 0 18px' }}>
          You can edit this later, but adding it now makes the KB easier to find in your
          grid and helps teammates decide whether to use it.
        </p>

        {error && (
          <div id="create-kb-error" role="alert" style={{
            padding: '8px 12px', borderRadius: 6, marginBottom: 12,
            fontSize: 12, color: '#fca5a5',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
          }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            disabled={creating}
            style={{
              padding: '6px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              color: '#aaa', backgroundColor: 'transparent',
              border: '1px solid #3a3a3a', borderRadius: 6,
              cursor: creating ? 'default' : 'pointer',
              opacity: creating ? 0.6 : 1,
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 14px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              color: 'var(--highlight-text-color, #000)',
              backgroundColor: 'var(--highlight-color, #eab308)',
              border: 'none', borderRadius: 6,
              cursor: canSubmit ? 'pointer' : 'default',
              opacity: canSubmit ? 1 : 0.5,
            }}
          >
            {creating && <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />}
            {creating ? 'Creating...' : 'Create'}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
