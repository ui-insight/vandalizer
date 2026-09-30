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
  const [pending, setPending] = useState(false)
  const submitting = useRef(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (submitting.current) return
    const err = getNameError(name, 'Folder name')
    if (err) {
      setError(err)
      return
    }
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
          <label htmlFor="folder-name-input" className="sr-only">Folder name</label>
          <input
            id="folder-name-input"
            autoFocus
            type="text"
            placeholder="Folder name"
            disabled={pending}
            value={name}
            maxLength={MAX_NAME_LENGTH}
            onChange={(e) => { setName(e.target.value); if (error) setError(null) }}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
          />
          {error && <p role="alert" className="mt-2 text-sm text-red-600">{error}</p>}
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
