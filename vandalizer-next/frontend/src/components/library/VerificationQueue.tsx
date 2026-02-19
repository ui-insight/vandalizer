import { useCallback, useEffect, useState } from 'react'
import { ShieldCheck, Clock, CheckCircle, XCircle, Eye } from 'lucide-react'
import { listVerificationQueue, myVerificationRequests, updateVerificationStatus } from '../../api/library'
import type { VerificationRequest, VerificationStatus } from '../../types/library'

type QueueView = 'pending' | 'mine'

function statusBadge(status: VerificationStatus) {
  switch (status) {
    case 'submitted':
      return { label: 'Submitted', className: 'bg-blue-50 text-blue-700 border-blue-200' }
    case 'in_review':
      return { label: 'In Review', className: 'bg-yellow-50 text-yellow-700 border-yellow-200' }
    case 'approved':
      return { label: 'Approved', className: 'bg-green-50 text-green-700 border-green-200' }
    case 'rejected':
      return { label: 'Rejected', className: 'bg-red-50 text-red-700 border-red-200' }
    default:
      return { label: status, className: 'bg-gray-50 text-gray-700 border-gray-200' }
  }
}

export function VerificationQueue() {
  const [view, setView] = useState<QueueView>('pending')
  const [requests, setRequests] = useState<VerificationRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [reviewingId, setReviewingId] = useState<string | null>(null)
  const [reviewNotes, setReviewNotes] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data =
        view === 'pending'
          ? await listVerificationQueue()
          : await myVerificationRequests()
      setRequests(data.requests)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [view])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleAction = async (uuid: string, action: 'approved' | 'rejected' | 'in_review') => {
    await updateVerificationStatus(uuid, action, reviewNotes.trim() || undefined)
    setReviewingId(null)
    setReviewNotes('')
    refresh()
  }

  return (
    <div>
      {/* View toggle */}
      <div className="flex items-center gap-2 mb-4">
        <button
          onClick={() => setView('pending')}
          className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
            view === 'pending'
              ? 'bg-gray-900 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Review Queue
        </button>
        <button
          onClick={() => setView('mine')}
          className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
            view === 'mine'
              ? 'bg-gray-900 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          My Submissions
        </button>
      </div>

      {loading ? (
        <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>
      ) : requests.length === 0 ? (
        <div className="text-sm text-gray-500 py-12 text-center">
          {view === 'pending' ? 'No pending verification requests.' : 'You have no submissions yet.'}
        </div>
      ) : (
        <div className="space-y-2">
          {requests.map((req) => {
            const badge = statusBadge(req.status)
            const isReviewing = reviewingId === req.uuid

            return (
              <div
                key={req.id}
                className="border border-gray-200 rounded-lg p-4 bg-white"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <ShieldCheck className="h-4 w-4 text-gray-400 shrink-0" />
                      <span className="text-sm font-semibold text-gray-900 truncate">
                        {req.item_name || req.summary || 'Untitled'}
                      </span>
                      <span
                        className={`text-xs px-2 py-0.5 rounded border shrink-0 ${badge.className}`}
                      >
                        {badge.label}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 space-x-3">
                      <span>{req.item_kind === 'workflow' ? 'Workflow' : 'Extraction'}</span>
                      {req.submitter_name && <span>by {req.submitter_name}</span>}
                      {req.submitted_at && (
                        <span>
                          <Clock className="inline h-3 w-3 mr-0.5" />
                          {new Date(req.submitted_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                    {req.description && (
                      <p className="text-xs text-gray-600 mt-1.5 line-clamp-2">
                        {req.description}
                      </p>
                    )}
                    {req.reviewer_notes && (
                      <p className="text-xs text-gray-500 mt-1 italic">
                        Reviewer: {req.reviewer_notes}
                      </p>
                    )}
                  </div>

                  {/* Actions for pending queue */}
                  {view === 'pending' &&
                    (req.status === 'submitted' || req.status === 'in_review') && (
                      <div className="flex items-center gap-1 shrink-0">
                        {!isReviewing ? (
                          <>
                            <button
                              onClick={() => setReviewingId(req.uuid)}
                              className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
                              title="Review"
                            >
                              <Eye className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleAction(req.uuid, 'approved')}
                              className="p-1.5 rounded hover:bg-green-50 text-green-600"
                              title="Approve"
                            >
                              <CheckCircle className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleAction(req.uuid, 'rejected')}
                              className="p-1.5 rounded hover:bg-red-50 text-red-600"
                              title="Reject"
                            >
                              <XCircle className="h-4 w-4" />
                            </button>
                          </>
                        ) : (
                          <div className="flex flex-col gap-2">
                            <textarea
                              value={reviewNotes}
                              onChange={(e) => setReviewNotes(e.target.value)}
                              placeholder="Review notes (optional)..."
                              rows={2}
                              className="text-xs border border-gray-300 rounded p-2 w-48 resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                            />
                            <div className="flex gap-1">
                              <button
                                onClick={() => handleAction(req.uuid, 'approved')}
                                className="flex-1 px-2 py-1 text-xs font-medium rounded bg-green-600 text-white hover:bg-green-700"
                              >
                                Approve
                              </button>
                              <button
                                onClick={() => handleAction(req.uuid, 'rejected')}
                                className="flex-1 px-2 py-1 text-xs font-medium rounded bg-red-600 text-white hover:bg-red-700"
                              >
                                Reject
                              </button>
                              <button
                                onClick={() => {
                                  setReviewingId(null)
                                  setReviewNotes('')
                                }}
                                className="px-2 py-1 text-xs font-medium rounded bg-gray-200 text-gray-700 hover:bg-gray-300"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
