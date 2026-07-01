import { useEffect, useState, type FormEvent } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { X, Library, Plus, Loader2 } from 'lucide-react'
import { listKnowledgeBasesV2, createKnowledgeBase } from '../../api/knowledge'
import type { KnowledgeBase } from '../../types/knowledge'

interface KBPickerModalProps {
  // Called with the chosen (or newly created) KB.
  onSelect: (uuid: string, title: string) => void
  onClose: () => void
  folderTitle: string
}

export function KBPickerModal({ onSelect, onClose, folderTitle }: KBPickerModalProps) {
  const [kbs, setKbs] = useState<KnowledgeBase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listKnowledgeBasesV2({ scope: 'mine' })
      .then(res => setKbs(res.items))
      .catch(() => setError('Could not load knowledge bases.'))
  }, [])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    const title = newTitle.trim()
    if (!title || busy) return
    setBusy(true)
    try {
      const kb = await createKnowledgeBase(title)
      onSelect(kb.uuid, kb.title)
    } catch {
      setError('Could not create knowledge base.')
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 700 }}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false }}>
      <div
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kb-picker-title"
      >
        <div className="mb-1 flex items-center justify-between">
          <h3 id="kb-picker-title" className="text-lg font-medium text-gray-900">Add to knowledge base</h3>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mb-3 text-sm text-gray-500">
          Add the documents in <strong className="text-gray-700">{folderTitle}</strong> to:
        </p>

        {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
        {!kbs && !error && (
          <p className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </p>
        )}

        {kbs && (
          <div className="max-h-64 overflow-y-auto rounded-md border border-gray-200">
            {kbs.length === 0 ? (
              <p className="px-3 py-4 text-sm text-gray-500">No knowledge bases yet — create one below.</p>
            ) : (
              <ul>
                {kbs.map(kb => (
                  <li key={kb.uuid}>
                    <button
                      disabled={busy}
                      onClick={() => { setBusy(true); onSelect(kb.uuid, kb.title) }}
                      className="flex w-full items-center gap-2.5 px-3 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04] disabled:opacity-50"
                    >
                      <Library className="h-4 w-4 shrink-0 text-gray-400" />
                      <span className="truncate">{kb.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {creating ? (
          <form onSubmit={handleCreate} className="mt-3 flex items-center gap-2">
            <input
              autoFocus
              type="text"
              placeholder="New knowledge base name"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-highlight focus:outline-none focus:ring-1 focus:ring-highlight"
            />
            <button
              type="submit"
              disabled={!newTitle.trim() || busy}
              className="rounded-md bg-highlight px-3 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50"
            >
              Create
            </button>
          </form>
        ) : (
          <button
            onClick={() => setCreating(true)}
            className="mt-3 flex items-center gap-1.5 text-sm font-medium text-gray-700 hover:text-gray-900"
          >
            <Plus className="h-4 w-4" /> New knowledge base
          </button>
        )}
      </div>
      </FocusTrap>
    </div>
  )
}
