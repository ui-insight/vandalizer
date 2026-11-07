import { FieldLabel, FieldMessage } from '../shared/FormField'
import { ActionButton } from '../shared/ActionButton'
import { usePanelEffect } from '../shared/usePanelEffect'
import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { Loader2 } from 'lucide-react'
import { isDuplicateName, MAX_NAME_LENGTH, getNameError, normalizeName } from '../../utils/nameValidation'

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
  const [titleError, setTitleError] = useState<string | null>(null)
  const titleRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    titleRef.current?.focus()
  }, [])

  usePanelEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !creating) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, creating])

  const canSubmit = title.trim().length > 0 && !creating

  const handleSubmit = async () => {
    if (!canSubmit) return
    const nameError = getNameError(title, 'Title')
    if (nameError) { setTitleError(nameError); titleRef.current?.focus(); return }
    if (existingTitles && isDuplicateName(title, existingTitles)) {
      setTitleError(`A knowledge base named "${title.trim()}" already exists. Choose a different name.`)
      titleRef.current?.focus()
      return
    }
    setTitleError(null)
    setCreating(true)
    setError(null)
    try {
      await onCreate(normalizeName(title), description.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create knowledge base')
      setCreating(false)
    }
  }

  return (
    <div
      onClick={() => { if (!creating) onClose() }}
      style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, fallbackFocus: '#create-kb-dialog-title', tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-kb-dialog-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: 'var(--workspace-canvas)', borderRadius: 'var(--workspace-radius-large)', width: 440, maxWidth: 'calc(100vw - 24px)',
          border: '1px solid var(--workspace-border)', maxHeight: 'calc(100dvh - 24px)', overflow: 'hidden', display: 'flex', flexDirection: 'column',
        }}
      >
        <div className="workspace-dialog-header"><h3 id="create-kb-dialog-title" tabIndex={-1} style={{ marginTop: 0, fontSize: 'var(--workspace-font-card-title)', fontWeight: 600, color: 'var(--workspace-text)', marginBottom: 'var(--workspace-space-6)' }}>
          Create Knowledge Base
        </h3></div>
        <div className="workspace-dialog-body">
        <p style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', margin: "0 0 var(--workspace-space-16)", lineHeight: 1.5 }}>
          A knowledge base groups documents and URLs so you can chat with them as one
          searchable corpus. A clear title and short description help your team (and
          future-you) understand what it covers.
        </p>

        <FieldLabel htmlFor="create-kb-title" required>Title</FieldLabel>
        <input
          id="create-kb-title"
          ref={titleRef}
          disabled={creating}
          maxLength={MAX_NAME_LENGTH}
          aria-required="true"
          value={title}
          onChange={(e) => { setTitle(e.target.value); setTitleError(null) }}
          onKeyDown={(e) => { if (e.key === 'Enter' && canSubmit) handleSubmit() }}
          placeholder="e.g. NIH Grant Proposals 2026"
          aria-invalid={!!titleError}
          aria-describedby={`create-kb-title-help${titleError ? ' create-kb-title-error' : ''}`}
          style={{
            width: '100%', padding: "var(--workspace-space-8) var(--workspace-space-12)", fontSize: 'var(--workspace-font-control)', fontFamily: 'inherit',
            backgroundColor: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)',
            color: 'var(--workspace-text)', marginBottom: 'var(--workspace-space-16)', boxSizing: 'border-box',
          }}
        />

        <FieldMessage id="create-kb-title-help">Up to {MAX_NAME_LENGTH} characters.</FieldMessage>
        {titleError && <FieldMessage id="create-kb-title-error" error>{titleError}</FieldMessage>}

        <FieldLabel htmlFor="create-kb-description" optional>Description</FieldLabel>
        <textarea
          id="create-kb-description"
          disabled={creating}
          aria-describedby="create-kb-description-help"
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
        <FieldMessage id="create-kb-description-help">Help teammates understand when to use this knowledge base. You can edit this later.</FieldMessage>

        {error && <FieldMessage id="create-kb-error" error>{error} Your entries are preserved; try again.</FieldMessage>}

        </div>
        <div className="workspace-dialog-footer">
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
