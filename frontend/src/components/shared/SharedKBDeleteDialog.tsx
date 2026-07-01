import { useEffect, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { AlertTriangle, X, Loader2, Users, Trash2 } from 'lucide-react'

export type SharedKBDeleteChoice = 'transfer' | 'unshare_and_delete'

interface Props {
  open: boolean
  kbTitle: string
  onCancel: () => void
  onChoose: (choice: SharedKBDeleteChoice) => Promise<void> | void
}

export function SharedKBDeleteDialog({ open, kbTitle, onCancel, onChoose }: Props) {
  const [busy, setBusy] = useState<SharedKBDeleteChoice | null>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && busy === null) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onCancel])

  if (!open) return null

  const handle = async (choice: SharedKBDeleteChoice) => {
    try {
      setBusy(choice)
      await onChoose(choice)
    } finally {
      setBusy(null)
    }
  }

  const disabled = busy !== null

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 1000 }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !disabled) onCancel()
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="shared-kb-delete-title"
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <h3 id="shared-kb-delete-title" className="text-lg font-medium text-gray-900">
            Delete shared knowledge base?
          </h3>
          <button
            type="button"
            onClick={onCancel}
            disabled={disabled}
            aria-label="Close"
            className="text-gray-400 hover:text-gray-600 disabled:opacity-40"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="mb-4 text-sm text-gray-600">
          <strong>{kbTitle}</strong> is currently shared with your team. What would you like to do?
        </p>

        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={() => handle('transfer')}
            disabled={disabled}
            className="flex items-start gap-3 rounded-md border border-gray-200 p-3 text-left hover:bg-gray-50 disabled:opacity-50"
          >
            <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-blue-50">
              {busy === 'transfer'
                ? <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                : <Users className="h-4 w-4 text-blue-600" />}
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-gray-900">Move to Team Library only</div>
              <div className="text-xs text-gray-600">
                Removes the knowledge base from My KBs but keeps it available to your team.
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => handle('unshare_and_delete')}
            disabled={disabled}
            className="flex items-start gap-3 rounded-md border border-red-200 p-3 text-left hover:bg-red-50 disabled:opacity-50"
          >
            <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-red-50">
              {busy === 'unshare_and_delete'
                ? <Loader2 className="h-4 w-4 animate-spin text-red-600" />
                : <Trash2 className="h-4 w-4 text-red-600" />}
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-red-700">Unshare and delete everywhere</div>
              <div className="text-xs text-gray-600">
                Permanently deletes the knowledge base and removes it from the Team Library. This cannot be undone.
              </div>
            </div>
          </button>
        </div>

        <div className="mt-4 flex items-start gap-2 rounded-md bg-amber-50 p-2 text-xs text-amber-800">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
          <span>Chats and workflows referencing this KB may lose context if it is deleted.</span>
        </div>

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={disabled}
            className="rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
