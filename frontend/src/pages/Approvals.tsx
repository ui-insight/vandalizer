import { useEffect, useState } from 'react'
import { CheckCircle, XCircle, Clock, MessageSquare, Eye } from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import * as api from '../api/approvals'
import type { ApprovalRequest } from '../api/approvals'

const STATUS_STYLES: Record<string, { icon: typeof Clock; color: string }> = {
  pending: { icon: Clock, color: 'text-amber-500' },
  approved: { icon: CheckCircle, color: 'text-green-500' },
  rejected: { icon: XCircle, color: 'text-red-500' },
}

function formatTime(ts: string | null): string {
  if (!ts) return '—'
  const d = new Date(ts)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function Approvals() {
  const { user } = useAuth()
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('pending')
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRequest | null>(null)
  const [comments, setComments] = useState('')
  const [processing, setProcessing] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.listApprovals(statusFilter || undefined)
      setApprovals(data.approvals)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [statusFilter])

  const handleApprove = async (uuid: string) => {
    setProcessing(true)
    try {
      await api.approveRequest(uuid, comments)
      setSelectedApproval(null)
      setComments('')
      load()
    } catch {
      // ignore
    } finally {
      setProcessing(false)
    }
  }

  const handleReject = async (uuid: string) => {
    setProcessing(true)
    try {
      await api.rejectRequest(uuid, comments)
      setSelectedApproval(null)
      setComments('')
      load()
    } catch {
      // ignore
    } finally {
      setProcessing(false)
    }
  }

  return (
    <PageLayout>
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CheckCircle className="h-6 w-6 text-gray-700" />
            <h1 className="text-2xl font-bold text-gray-900">Approval Queue</h1>
          </div>
          <div className="flex gap-2">
            {['pending', 'approved', 'rejected', ''].map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                  statusFilter === s
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                {s || 'All'}
              </button>
            ))}
          </div>
        </div>

        {/* Approval detail modal */}
        {selectedApproval && (
          <div className="mb-4 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-medium">Review: {selectedApproval.step_name}</h3>
              <button
                onClick={() => setSelectedApproval(null)}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Close
              </button>
            </div>

            {selectedApproval.review_instructions && (
              <div className="mb-4 rounded-lg bg-blue-50 p-3 text-sm text-blue-800">
                {selectedApproval.review_instructions}
              </div>
            )}

            <div className="mb-4">
              <h4 className="mb-2 text-sm font-medium text-gray-700">Data for Review</h4>
              <pre className="max-h-64 overflow-auto rounded-lg bg-gray-50 p-3 text-xs">
                {JSON.stringify(selectedApproval.data_for_review, null, 2)}
              </pre>
            </div>

            {selectedApproval.status === 'pending' && (
              <>
                <div className="mb-3">
                  <label className="mb-1 block text-sm text-gray-600">Comments</label>
                  <textarea
                    value={comments}
                    onChange={(e) => setComments(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                    rows={3}
                    placeholder="Optional reviewer comments..."
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprove(selectedApproval.uuid)}
                    disabled={processing}
                    className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                  >
                    <CheckCircle className="h-4 w-4" />
                    Approve
                  </button>
                  <button
                    onClick={() => handleReject(selectedApproval.uuid)}
                    disabled={processing}
                    className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    <XCircle className="h-4 w-4" />
                    Reject
                  </button>
                </div>
              </>
            )}

            {selectedApproval.status !== 'pending' && (
              <div className="rounded-lg bg-gray-50 p-3 text-sm">
                <span className="font-medium">Decision:</span> {selectedApproval.status} by{' '}
                {selectedApproval.reviewer_user_id || 'unknown'}
                {selectedApproval.reviewer_comments && (
                  <p className="mt-1 text-gray-600">"{selectedApproval.reviewer_comments}"</p>
                )}
              </div>
            )}
          </div>
        )}

        {/* List */}
        <div className="space-y-2">
          {loading ? (
            <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-500">
              Loading...
            </div>
          ) : approvals.length === 0 ? (
            <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-gray-500">
              <Clock className="mx-auto mb-2 h-8 w-8 text-gray-300" />
              <p>No {statusFilter || ''} approvals found</p>
            </div>
          ) : (
            approvals.map((a) => {
              const style = STATUS_STYLES[a.status] || STATUS_STYLES.pending
              const Icon = style.icon
              return (
                <div
                  key={a.uuid}
                  className="flex items-center gap-4 rounded-lg border border-gray-200 bg-white px-4 py-3 hover:bg-gray-50"
                >
                  <Icon className={`h-5 w-5 ${style.color}`} />
                  <div className="flex-1">
                    <div className="font-medium text-gray-900">{a.step_name}</div>
                    <div className="text-sm text-gray-500">
                      {a.review_instructions ? a.review_instructions.slice(0, 80) : 'No instructions'}
                    </div>
                  </div>
                  <div className="text-right text-sm text-gray-500">
                    {formatTime(a.created_at)}
                  </div>
                  <button
                    onClick={() => {
                      setSelectedApproval(a)
                      setComments('')
                    }}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
                  >
                    <Eye className="h-4 w-4" />
                    Review
                  </button>
                </div>
              )
            })
          )}
        </div>
      </div>
    </PageLayout>
  )
}
