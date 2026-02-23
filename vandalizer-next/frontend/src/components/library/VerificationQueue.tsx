import { useCallback, useEffect, useState } from 'react'
import { ShieldCheck, Clock, CheckCircle, XCircle, Eye, Search, ChevronDown, ChevronRight, Tag, FileText, RotateCcw } from 'lucide-react'
import { listVerificationQueue, myVerificationRequests, updateVerificationStatus } from '../../api/library'
import type { VerificationRequest, VerificationStatus } from '../../types/library'

type QueueView = 'pending' | 'mine'
type StatusFilter = '' | 'submitted' | 'in_review' | 'returned'

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
    case 'returned':
      return { label: 'Returned', className: 'bg-orange-50 text-orange-700 border-orange-200' }
    default:
      return { label: status, className: 'bg-gray-50 text-gray-700 border-gray-200' }
  }
}

function tierBadgeClass(tier: string | null | undefined) {
  switch (tier) {
    case 'excellent': return 'bg-green-50 text-green-700 border-green-200'
    case 'good': return 'bg-blue-50 text-blue-700 border-blue-200'
    case 'fair': return 'bg-yellow-50 text-yellow-700 border-yellow-200'
    default: return 'bg-gray-50 text-gray-500 border-gray-200'
  }
}

function DetailSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">{label}</div>
      <div className="text-sm text-gray-700">{children}</div>
    </div>
  )
}

function ListDetail({ label, items }: { label: string; items?: string[] }) {
  if (!items || items.length === 0) return null
  return (
    <DetailSection label={label}>
      <ul className="list-disc list-inside space-y-0.5">
        {items.map((item, i) => (
          <li key={i} className="text-sm text-gray-700">{item}</li>
        ))}
      </ul>
    </DetailSection>
  )
}

export function VerificationQueue() {
  const [view, setView] = useState<QueueView>('pending')
  const [requests, setRequests] = useState<VerificationRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [reviewingId, setReviewingId] = useState<string | null>(null)
  const [reviewNotes, setReviewNotes] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('')

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data =
        view === 'pending'
          ? await listVerificationQueue(statusFilter || undefined)
          : await myVerificationRequests()
      setRequests(data.requests)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [view, statusFilter])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleAction = async (uuid: string, action: 'approved' | 'rejected' | 'in_review' | 'returned') => {
    await updateVerificationStatus(uuid, action, reviewNotes.trim() || undefined)
    setReviewingId(null)
    setReviewNotes('')
    refresh()
  }

  const filtered = requests.filter(r => {
    // Client-side status filtering for "mine" view
    if (view === 'mine' && statusFilter && r.status !== statusFilter) return false
    // Search filtering
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return (
        (r.item_name || '').toLowerCase().includes(q) ||
        (r.summary || '').toLowerCase().includes(q) ||
        (r.submitter_name || '').toLowerCase().includes(q) ||
        (r.description || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  return (
    <div>
      {/* Search + view toggle + status filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search requests..."
            className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
          />
        </div>
        <div className="flex items-center gap-2">
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
      </div>

      {/* Status filter chips */}
      {(view === 'pending' || view === 'mine') && (
        <div className="flex items-center gap-2 mb-4">
          {([['', 'All'], ['submitted', 'Submitted'], ['in_review', 'In Review'], ...(view === 'mine' ? [['returned' as StatusFilter, 'Returned'] as [StatusFilter, string]] : [])] as [StatusFilter, string][]).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setStatusFilter(val)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                statusFilter === val
                  ? 'bg-gray-900 text-white border-gray-900'
                  : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="text-sm text-gray-500 py-12 text-center">
          {view === 'pending' ? 'No pending verification requests.' : 'You have no submissions yet.'}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((req) => {
            const badge = statusBadge(req.status)
            const isReviewing = reviewingId === req.uuid
            const isExpanded = expandedId === req.uuid

            return (
              <div
                key={req.id}
                className="border border-gray-200 rounded-lg bg-white"
              >
                <div className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <button
                          onClick={() => setExpandedId(isExpanded ? null : req.uuid)}
                          className="p-0.5 rounded hover:bg-gray-100 text-gray-400 shrink-0"
                        >
                          {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </button>
                        <ShieldCheck className="h-4 w-4 text-gray-400 shrink-0" />
                        <span className="text-sm font-semibold text-gray-900 truncate">
                          {req.item_name || req.summary || 'Untitled'}
                        </span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded border shrink-0 ${badge.className}`}
                        >
                          {badge.label}
                        </span>
                        {req.validation_score != null && (
                          <span className={`text-xs px-2 py-0.5 rounded border shrink-0 ${tierBadgeClass(req.validation_tier)}`}>
                            {Math.round(req.validation_score)}%
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 space-x-3 ml-9">
                        <span>{req.item_kind === 'workflow' ? 'Workflow' : 'Extraction'}</span>
                        {req.submitter_name && <span>by {req.submitter_name}</span>}
                        {req.submitter_org && <span>({req.submitter_org})</span>}
                        {req.submitted_at && (
                          <span>
                            <Clock className="inline h-3 w-3 mr-0.5" />
                            {new Date(req.submitted_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                      {!isExpanded && req.description && (
                        <p className="text-xs text-gray-600 mt-1.5 line-clamp-2 ml-9">
                          {req.description}
                        </p>
                      )}
                      {req.reviewer_notes && (
                        <p className="text-xs text-gray-500 mt-1 italic ml-9">
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
                              <button
                                onClick={() => setReviewingId(req.uuid)}
                                className="p-1.5 rounded hover:bg-orange-50 text-orange-600"
                                title="Return for Improvement"
                              >
                                <RotateCcw className="h-4 w-4" />
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
                                  onClick={() => handleAction(req.uuid, 'returned')}
                                  className="flex-1 px-2 py-1 text-xs font-medium rounded bg-orange-500 text-white hover:bg-orange-600"
                                >
                                  Return
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

                {/* Expandable detail section */}
                {isExpanded && (
                  <div className="border-t border-gray-100 px-4 py-3 bg-gray-50/50">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 ml-9">
                      {req.validation_snapshot && (
                        <DetailSection label="Validation Results">
                          {req.item_kind === 'search_set' || req.item_kind === 'search-set' ? (
                            <div className="space-y-1">
                              {(req.validation_snapshot as Record<string, unknown>).aggregate_accuracy != null && (
                                <div className="text-xs">Accuracy: <span className="font-medium">{Math.round(((req.validation_snapshot as Record<string, unknown>).aggregate_accuracy as number) * 100)}%</span></div>
                              )}
                              {(req.validation_snapshot as Record<string, unknown>).aggregate_consistency != null && (
                                <div className="text-xs">Consistency: <span className="font-medium">{Math.round(((req.validation_snapshot as Record<string, unknown>).aggregate_consistency as number) * 100)}%</span></div>
                              )}
                            </div>
                          ) : (
                            <div className="space-y-1">
                              {(req.validation_snapshot as Record<string, unknown>).grade && (
                                <div className="text-xs">Grade: <span className="font-semibold">{(req.validation_snapshot as Record<string, unknown>).grade as string}</span></div>
                              )}
                              {(req.validation_snapshot as Record<string, unknown>).summary && (
                                <div className="text-xs">{(req.validation_snapshot as Record<string, unknown>).summary as string}</div>
                              )}
                            </div>
                          )}
                          {req.validation_score != null && (
                            <div className="text-xs mt-1">Quality Score: <span className="font-medium">{Math.round(req.validation_score)}%</span> ({req.validation_tier || 'unrated'})</div>
                          )}
                        </DetailSection>
                      )}
                      {req.return_guidance && (
                        <DetailSection label="Improvement Guidance">
                          <p className="whitespace-pre-wrap text-orange-700">{req.return_guidance}</p>
                        </DetailSection>
                      )}
                      {req.description && (
                        <DetailSection label="Description">
                          <p className="whitespace-pre-wrap">{req.description}</p>
                        </DetailSection>
                      )}
                      {req.run_instructions && (
                        <DetailSection label="Run Instructions">
                          <p className="whitespace-pre-wrap">{req.run_instructions}</p>
                        </DetailSection>
                      )}
                      {req.evaluation_notes && (
                        <DetailSection label="Evaluation Notes">
                          <p className="whitespace-pre-wrap">{req.evaluation_notes}</p>
                        </DetailSection>
                      )}
                      {req.known_limitations && (
                        <DetailSection label="Known Limitations">
                          <p className="whitespace-pre-wrap">{req.known_limitations}</p>
                        </DetailSection>
                      )}
                      <ListDetail label="Example Inputs" items={req.example_inputs} />
                      <ListDetail label="Expected Outputs" items={req.expected_outputs} />
                      <ListDetail label="Dependencies" items={req.dependencies} />
                      {req.intended_use_tags && req.intended_use_tags.length > 0 && (
                        <DetailSection label="Intended Use Tags">
                          <div className="flex flex-wrap gap-1.5">
                            {req.intended_use_tags.map((tag, i) => (
                              <span key={i} className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                                <Tag className="h-3 w-3" />
                                {tag}
                              </span>
                            ))}
                          </div>
                        </DetailSection>
                      )}
                      {req.test_files && req.test_files.length > 0 && (
                        <DetailSection label="Test Files">
                          <div className="space-y-1">
                            {req.test_files.map((f, i) => (
                              <div key={i} className="flex items-center gap-1.5 text-xs text-gray-600">
                                <FileText className="h-3 w-3" />
                                {f.original_name}
                              </div>
                            ))}
                          </div>
                        </DetailSection>
                      )}
                      {req.category && (
                        <DetailSection label="Category">
                          <span>{req.category}</span>
                        </DetailSection>
                      )}
                      {req.item_version_hash && (
                        <DetailSection label="Version Hash">
                          <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded font-mono">{req.item_version_hash}</code>
                        </DetailSection>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
