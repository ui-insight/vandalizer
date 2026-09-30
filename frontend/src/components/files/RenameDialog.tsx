import { useRef, useState, type FormEvent } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X } from 'lucide-react'
import { MAX_NAME_LENGTH, getNameError, normalizeName } from '../../utils/nameValidation'

interface RenameDialogProps {
  currentName: string
  onSubmit: (newName: string) => void | Promise<void>
  onClose: () => void
}

export function RenameDialog({ currentName, onSubmit, onClose }: RenameDialogProps) {
  const [name, setName] = useState(currentName)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const submitting = useRef(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (submitting.current) return
    const err = getNameError(name)
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
        aria-labelledby="rename-dialog-title"
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="rename-dialog-title" className="text-lg font-medium text-gray-900">Rename</h3>
          <button disabled={pending} onClick={onClose} aria-label="Close" className="text-gray-500 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mb-3 break-words text-sm text-gray-600">Renaming: {currentName}</p>
        <form onSubmit={handleSubmit}>
          <label htmlFor="rename-input" className="sr-only">New name</label>
          <input
            id="rename-input"
            autoFocus
            type="text"
            disabled={pending}
            value={name}
            maxLength={MAX_NAME_LENGTH}
            onChange={(e) => { setName(e.target.value); if (error) setError(null) }}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
          />
          {error && <p role="alert" className="mt-2 text-sm text-red-600">{error}</p>}
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              disabled={pending}
              onClick={onClose}
              className="rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={pending}
              className="rounded-md bg-highlight px-3 py-2 text-sm font-bold text-highlight-text hover:brightness-90"
            >
              {pending ? 'Renaming…' : 'Rename'}
            </button>
          </div>
        </form>
      </div>
      </FocusTrap>
    </div>
  )
}
