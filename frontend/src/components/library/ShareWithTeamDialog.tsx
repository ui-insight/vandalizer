import { usePanelEffect } from '../shared/usePanelEffect'
import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X } from 'lucide-react'

export interface ShareTeamOption {
  id: string
  name: string
}

interface Props {
  itemName: string
  /** The destination when the caller can't offer a choice (a KB shares with its own team). */
  teamName?: string
  /**
   * Teams the item can be sent to. With more than one, the dialog shows a
   * picker defaulting to ``defaultTeamId``; the chosen id goes to onConfirm.
   */
  teams?: ShareTeamOption[]
  defaultTeamId?: string
  createsIndependentCopy?: boolean
  busy?: boolean
  onCancel: () => void
  onConfirm: (comment: string, teamId?: string) => void | Promise<void>
}

export function ShareWithTeamDialog({ itemName, teamName, teams, defaultTeamId, createsIndependentCopy = false, busy, onCancel, onConfirm }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const inFlight = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [teamId, setTeamId] = useState<string | undefined>(
    () => (teams?.some((t) => t.id === defaultTeamId) ? defaultTeamId : teams?.[0]?.id),
  )
  const destination = teams?.find((t) => t.id === teamId)?.name ?? teamName
  const canPick = (teams?.length ?? 0) > 1

  const handleSubmit = async () => {
    if (inFlight.current || busy) return
    inFlight.current = true
    setError(null)
    setSubmitting(true)
    try {
      await onConfirm(comment.trim(), teamId)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not share. Your note has been kept; try again.')
    } finally {
      inFlight.current = false
      setSubmitting(false)
    }
  }

  const errorRef = useRef<HTMLParagraphElement>(null)
  const isBusy = busy || submitting
  useEffect(() => { if (error && !isBusy) errorRef.current?.focus() }, [error, isBusy])

  usePanelEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape' && !isBusy && !inFlight.current) onCancel() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onCancel, isBusy])

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/40" style={{ zIndex: 700 }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, fallbackFocus: () => dialogRef.current!, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Share with team"
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-6"
        style={{ margin: 'var(--workspace-space-12)', maxHeight: 'calc(100dvh - 24px)', overflowY: 'auto', overflowWrap: 'anywhere' }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Share with team</h3>
          <button aria-label="Close sharing dialog" onClick={onCancel} className="p-1 text-gray-400 hover:text-gray-600 rounded" disabled={isBusy}>
            <X size={18} />
          </button>
        </div>

        {canPick ? (
          <>
            <p className="text-sm text-gray-700 mb-3">
              Sharing <span className="font-medium">{itemName}</span>. Teammates will get a
              bell notification and an email.
            </p>
            <div className="mb-4">
              <label htmlFor="share-team-select" className="block text-sm font-medium text-gray-700 mb-1">
                Team
              </label>
              <select
                id="share-team-select"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                disabled={isBusy}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-highlight"
              >
                {teams!.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}{t.id === defaultTeamId ? ' (current team)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </>
        ) : (
          <p className="text-sm text-gray-700 mb-4">
            Sharing <span className="font-medium">{itemName}</span>
            {destination ? <> with <span className="font-medium">{destination}</span></> : null}.
            Teammates will get a bell notification and an email.
          </p>
        )}

        {createsIndependentCopy && <p className="mb-4 text-sm text-gray-600">This creates an independent team copy. Later edits to your original or this copy do not update the other.</p>}
        <div>
          <label htmlFor="share-team-note" className="block text-sm font-medium text-gray-700 mb-1">
            Add a note (optional)
          </label>
          <textarea
            id="share-team-note"
            disabled={isBusy}
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

        {error && <p ref={errorRef} tabIndex={-1} role="alert" className="text-sm text-red-800 mt-3">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2 mt-4">
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
            {isBusy ? 'Sharing…' : destination ? `Share with ${destination}` : 'Share'}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
