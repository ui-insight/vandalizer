import { FieldLabel, FieldMessage } from '../shared/FormField'
import { ActionButton } from '../shared/ActionButton'
import { useRef, useState, type FormEvent } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X } from 'lucide-react'
import { MAX_NAME_LENGTH, getNameError, normalizeName } from '../../utils/nameValidation'

interface CreateFolderDialogProps {
  onSubmit: (name: string) => void | Promise<void>
  onClose: () => void
  title?: string
}

export function CreateFolderDialog({ onSubmit, onClose, title }: CreateFolderDialogProps) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [nameError, setNameError] = useState<string | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const [pending, setPending] = useState(false)
  const submitting = useRef(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (submitting.current) return
    const err = getNameError(name, 'Folder name')
    if (err) {
      setNameError(err)
      nameRef.current?.focus()
      return
    }
    setNameError(null)
    submitting.current = true
    setPending(true)
    setError(null)
    try { await onSubmit(normalizeName(name)) }
    catch (error) { setError(`${error instanceof Error ? error.message : 'Could not save the name'}. Your entry is preserved; try again.`) }
    finally { submitting.current = false; setPending(false) }
  }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 700 }}
      onKeyDown={(e) => {
        if (e.key === 'Escape' && !submitting.current) onClose()
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
        style={{ maxWidth: 'calc(100vw - 24px)', maxHeight: '90dvh', overflowY: 'auto' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-folder-dialog-title"
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="create-folder-dialog-title" className="text-lg font-medium text-gray-900">{title || 'New Folder'}</h3>
          <ActionButton variant="quiet" iconOnly disabled={pending} onClick={onClose} aria-label="Close" >
            <X className="h-5 w-5" />
          </ActionButton>
        </div>
        <form onSubmit={handleSubmit}>
          <FieldLabel htmlFor="folder-name-input" required>Folder name</FieldLabel>
          <input
            id="folder-name-input"
            ref={nameRef}
            aria-required="true"
            aria-invalid={!!nameError}
            aria-describedby={`folder-name-help${nameError ? ' folder-name-error' : ''}${error ? ' folder-save-error' : ''}`}
            autoFocus
            type="text"
            placeholder="Folder name"
            disabled={pending}
            value={name}
            maxLength={MAX_NAME_LENGTH}
            onChange={(e) => { setName(e.target.value); if (error) setError(null); if (nameError) setNameError(null) }}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
          />
          <FieldMessage id="folder-name-help">Up to {MAX_NAME_LENGTH} characters.</FieldMessage>
          {nameError && <FieldMessage id="folder-name-error" error>{nameError}</FieldMessage>}
          {error && <FieldMessage id="folder-save-error" error>{error}</FieldMessage>}
          <div className="mt-4 flex justify-end gap-2">
            <ActionButton variant="secondary"
              type="button"
              disabled={pending}
              onClick={onClose}

            >
              Cancel
            </ActionButton>
            <ActionButton variant="primary" aria-busy={pending}
              type="submit"
              disabled={pending}

            >
              {pending ? 'Creating…' : 'Create'}
            </ActionButton>
          </div>
        </form>
      </div>
      </FocusTrap>
    </div>
  )
}
