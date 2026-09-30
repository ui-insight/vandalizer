import { ActionButton } from '../shared/ActionButton'
import { usePanelEffect } from '../shared/usePanelEffect'
import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { Loader2 } from 'lucide-react'
import { isDuplicateName } from '../../utils/nameValidation'

interface CreateKBModalProps {
  onClose: () => void
  onCreate: (title: string, description: string) => Promise<void>
  /** Titles of the user's existing KBs, for the pre-submit duplicate check. */
  existingTitles?: string[]
}

export function CreateKBModal({ onClose, onCreate, existingTitles }: CreateKBModalProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const titleRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    titleRef.current?.focus()
  }, [])

  usePanelEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const canSubmit = title.trim().length > 0 && !creating

  const handleSubmit = async () => {
    if (!canSubmit) return
    if (existingTitles && isDuplicateName(title, existingTitles)) {
      setError(`A knowledge base named "${title.trim()}" already exists. Choose a different name.`)
      return
    }
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
          backgroundColor: 'var(--workspace-canvas)', borderRadius: 'var(--workspace-radius-large)', padding: 'var(--workspace-space-24)', width: 440,
          border: '1px solid var(--workspace-border)', maxHeight: '85vh', overflowY: 'auto',
        }}
      >
        <div style={{ fontSize: 'var(--workspace-font-card-title)', fontWeight: 600, color: 'var(--workspace-text)', marginBottom: 'var(--workspace-space-6)' }}>
          Create Knowledge Base
        </div>
        <p style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', margin: "0 0 var(--workspace-space-16)", lineHeight: 1.5 }}>
          A knowledge base groups documents and URLs so you can chat with them as one
          searchable corpus. A clear title and short description help your team (and
          future-you) understand what it covers.
        </p>

        <label htmlFor="create-kb-title" style={{ display: 'block', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: 'var(--workspace-muted)', marginBottom: 'var(--workspace-space-4)' }}>
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
            width: '100%', padding: "var(--workspace-space-8) var(--workspace-space-12)", fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
            backgroundColor: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
            color: 'var(--workspace-text)', marginBottom: 'var(--workspace-space-16)', boxSizing: 'border-box',
          }}
        />

        <label htmlFor="create-kb-description" style={{ display: 'block', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: 'var(--workspace-muted)', marginBottom: 'var(--workspace-space-4)' }}>
          Description
        </label>
        <textarea
          id="create-kb-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What is in this knowledge base, and what should it be used for?"
          rows={4}
          style={{
            width: '100%', padding: "var(--workspace-space-8) var(--workspace-space-12)", fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
            backgroundColor: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
            color: 'var(--workspace-text)', marginBottom: 'var(--workspace-space-6)', resize: 'vertical',
            boxSizing: 'border-box', lineHeight: 1.5,
          }}
        />
        <p style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', margin: "0 0 var(--workspace-space-20)" }}>
          You can edit this later, but adding it now makes the KB easier to find in your
          grid and helps teammates decide whether to use it.
        </p>

        {error && (
          <div id="create-kb-error" role="alert" style={{
            padding: "var(--workspace-space-8) var(--workspace-space-12)", borderRadius: 'var(--workspace-radius-small)', marginBottom: 'var(--workspace-space-12)',
            fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-danger)',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
          }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 'var(--workspace-space-8)', justifyContent: 'flex-end' }}>
          <ActionButton variant="secondary"
            onClick={onClose}
            disabled={creating}

          >
            Cancel
          </ActionButton>
          <ActionButton variant="primary" aria-busy={creating}
            onClick={handleSubmit}
            disabled={!canSubmit}

          >
            {creating && <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />}
            {creating ? 'Creating...' : 'Create'}
          </ActionButton>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
