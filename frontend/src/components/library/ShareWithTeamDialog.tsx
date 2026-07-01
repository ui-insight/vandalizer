import { useEffect, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { X } from 'lucide-react'

interface Props {
  itemName: string
  teamName?: string
  busy?: boolean
  onCancel: () => void
  onConfirm: (comment: string) => void | Promise<void>
}

export function ShareWithTeamDialog({ itemName, teamName, busy, onCancel, onConfirm }: Props) {
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      await onConfirm(comment.trim())
    } finally {
      setSubmitting(false)
    }
  }

  const isBusy = busy || submitting

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onCancel])

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/40" style={{ zIndex: 700 }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Share with team"
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-6"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Share with team</h3>
          <button onClick={onCancel} className="p-1 text-gray-400 hover:text-gray-600 rounded" disabled={isBusy}>
            <X size={18} />
          </button>
        </div>

        <p className="text-sm text-gray-700 mb-4">
          Sharing <span className="font-medium">{itemName}</span>
          {teamName ? <> with <span className="font-medium">{teamName}</span></> : null}.
          Teammates will get a bell notification and an email.
        </p>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Add a note (optional)
          </label>
          <textarea
            value={comment}
            onChange={e => setComment(e.target.value)}
            rows={4}
            maxLength={1000}
            placeholder="Why are you sharing this? Anything teammates should know?"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight resize-none"
            autoFocus
          />
          <div className="text-xs text-gray-500 text-right mt-1">{comment.length}/1000</div>
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onCancel}
            disabled={isBusy}
            className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isBusy}
            className="px-4 py-2 text-sm font-bold text-highlight-text bg-highlight hover:brightness-90 rounded-lg disabled:opacity-50"
          >
            {isBusy ? 'Sharing…' : 'Share'}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
