import { useState, type FormEvent } from 'react'
import { X } from 'lucide-react'

interface CreateFolderDialogProps {
  onSubmit: (name: string) => void
  onClose: () => void
  title?: string
}

export function CreateFolderDialog({ onSubmit, onClose, title }: CreateFolderDialogProps) {
  const [name, setName] = useState('')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (name.trim()) onSubmit(name.trim())
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
        aria-labelledby="create-folder-dialog-title"
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="create-folder-dialog-title" className="text-lg font-medium text-gray-900">{title || 'New Folder'}</h3>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <label htmlFor="folder-name-input" className="sr-only">Folder name</label>
          <input
            id="folder-name-input"
            autoFocus
            type="text"
            placeholder="Folder name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
          />
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
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
