import { useState, type FormEvent } from 'react'
import { X } from 'lucide-react'

interface RenameDialogProps {
  currentName: string
  onSubmit: (newName: string) => void
  onClose: () => void
}

export function RenameDialog({ currentName, onSubmit, onClose }: RenameDialogProps) {
  const [name, setName] = useState(currentName)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (name.trim()) onSubmit(name.trim())
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-medium text-gray-900">Rename</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <input
            autoFocus
            type="text"
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
              Rename
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
