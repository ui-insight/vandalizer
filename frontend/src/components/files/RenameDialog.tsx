import { useState, type FormEvent } from 'react'
import { X } from 'lucide-react'
import { MAX_NAME_LENGTH, getNameError, normalizeName } from '../../utils/nameValidation'

interface RenameDialogProps {
  currentName: string
  onSubmit: (newName: string) => void
  onClose: () => void
}

export function RenameDialog({ currentName, onSubmit, onClose }: RenameDialogProps) {
  const [name, setName] = useState(currentName)
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const err = getNameError(name)
    if (err) {
      setError(err)
      return
    }
    onSubmit(normalizeName(name))
  }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 700 }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose()
      }}
    >
      <div
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rename-dialog-title"
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="rename-dialog-title" className="text-lg font-medium text-gray-900">Rename</h3>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <label htmlFor="rename-input" className="sr-only">New name</label>
          <input
            id="rename-input"
            autoFocus
            type="text"
            value={name}
            maxLength={MAX_NAME_LENGTH}
            onChange={(e) => { setName(e.target.value); if (error) setError(null) }}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
          />
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-md bg-highlight px-3 py-2 text-sm font-bold text-highlight-text hover:brightness-90"
            >
              Rename
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
