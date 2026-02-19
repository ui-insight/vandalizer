import { useState } from 'react'
import { X, ExternalLink, Trash2, Calendar, Tag, ShieldCheck } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { submitForVerification } from '../../api/library'
import type { LibraryItem } from '../../types/library'

interface Props {
  item: LibraryItem
  onClose: () => void
  onRemove: (id: string) => void
}

export function LibraryItemDetails({ item, onClose, onRemove }: Props) {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState<'success' | 'error' | null>(null)
  const [submitError, setSubmitError] = useState('')
  const kindLabel =
    item.kind === 'workflow'
      ? 'Workflow'
      : item.set_type === 'prompt'
        ? 'Prompt'
        : item.set_type === 'formatter'
          ? 'Formatter'
          : 'Extraction Task'

  const formattedDate = item.created_at
    ? new Date(item.created_at).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    : 'Unknown'

  const handleUse = () => {
    if (item.kind === 'workflow') {
      navigate({ to: '/', search: { openWorkflow: item.item_id } })
    } else {
      navigate({ to: '/', search: { openExtraction: item.item_id } })
    }
  }

  const handleSubmitForVerification = async () => {
    setSubmitting(true)
    setSubmitResult(null)
    setSubmitError('')
    try {
      await submitForVerification({
        item_kind: item.kind,
        item_id: item.item_id,
        summary: item.name,
      })
      setSubmitResult('success')
    } catch (err: unknown) {
      setSubmitResult('error')
      setSubmitError(err instanceof Error ? err.message : 'Failed to submit')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="w-80 border-l border-gray-200 bg-white flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-900 truncate">Details</h3>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto p-4 space-y-5">
        {/* Title */}
        <div>
          <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Name</label>
          <p className="text-sm font-medium text-gray-900">{item.name}</p>
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Description</label>
          <p className="text-sm text-gray-600">
            {item.description || item.note || 'No description'}
          </p>
        </div>

        {/* Type */}
        <div>
          <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Type</label>
          <span className="inline-flex items-center gap-1.5 text-sm text-gray-700">
            <Tag className="h-3.5 w-3.5 text-gray-400" />
            {kindLabel}
          </span>
        </div>

        {/* Created date */}
        <div>
          <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Created</label>
          <span className="inline-flex items-center gap-1.5 text-sm text-gray-700">
            <Calendar className="h-3.5 w-3.5 text-gray-400" />
            {formattedDate}
          </span>
        </div>

        {/* Tags */}
        {item.tags.length > 0 && (
          <div>
            <label className="block text-xs font-medium uppercase text-gray-400 mb-1">Tags</label>
            <div className="flex flex-wrap gap-1.5">
              {item.tags.map((tag) => (
                <span
                  key={tag}
                  className="text-xs px-2 py-0.5 rounded bg-yellow-50 text-yellow-700 border border-yellow-200"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Status indicators */}
        <div className="flex items-center gap-3 text-xs text-gray-500">
          {item.pinned && <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-600">Pinned</span>}
          {item.favorited && <span className="px-2 py-0.5 rounded bg-yellow-50 text-yellow-600">Favorited</span>}
          {item.verified && <span className="px-2 py-0.5 rounded bg-green-50 text-green-600">Verified</span>}
        </div>
      </div>

      {/* Footer actions */}
      <div className="border-t border-gray-200 p-4 space-y-2">
        <button
          onClick={handleUse}
          className="flex w-full items-center justify-center gap-1.5 rounded-md bg-highlight px-4 py-2 text-sm font-bold text-highlight-text hover:brightness-90"
        >
          <ExternalLink className="h-4 w-4" />
          {item.kind === 'workflow' ? 'Open' : 'Use'}
        </button>
        {!item.verified && (
          <button
            onClick={handleSubmitForVerification}
            disabled={submitting || submitResult === 'success'}
            className="flex w-full items-center justify-center gap-1.5 rounded-md border border-green-200 px-4 py-2 text-sm font-medium text-green-700 hover:bg-green-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ShieldCheck className="h-4 w-4" />
            {submitting
              ? 'Submitting...'
              : submitResult === 'success'
                ? 'Submitted!'
                : 'Submit for Verification'}
          </button>
        )}
        {submitResult === 'error' && (
          <p className="text-xs text-red-500 text-center">{submitError}</p>
        )}
        <button
          onClick={() => onRemove(item.id)}
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
        >
          <Trash2 className="h-4 w-4" />
          Delete
        </button>
      </div>
    </div>
  )
}
