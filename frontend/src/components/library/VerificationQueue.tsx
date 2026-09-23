import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { ShieldCheck, Clock, Search, ChevronDown, ChevronRight, Tag, FileText, ExternalLink, Pin, Wrench, UserCheck } from 'lucide-react'
import { listVerificationQueue, myVerificationRequests, updateVerificationStatus } from '../../api/library'
import type { VerificationRequest, VerificationStatus } from '../../types/library'
import { AuthorChip } from '../shared/AuthorChip'
import { useAuth } from '../../hooks/useAuth'
import { ExaminerValidationDrawer } from './ExaminerValidationDrawer'

type QueueView = 'pending' | 'mine'
type StatusFilter = '' | 'submitted' | 'in_review' | 'returned' | 'pending_admin_validation'

function statusBadge(status: VerificationStatus) {
  switch (status) {
    case 'submitted':
      return { label: 'Submitted', className: 'bg-blue-50 text-blue-700 border-blue-200' }
    case 'in_review':
      return { label: 'In Review', className: 'bg-yellow-50 text-yellow-700 border-yellow-200' }
    case 'approved':
      return { label: 'Accepted', className: 'bg-green-50 text-green-700 border-green-200' }
    case 'rejected':
      return { label: 'Declined', className: 'bg-red-50 text-red-700 border-red-200' }
    case 'returned':
      return { label: 'Sent back', className: 'bg-orange-50 text-orange-700 border-orange-200' }
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

export function VerificationQueue({ focusRequestUuid }: { focusRequestUuid?: string } = {}) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [view, setView] = useState<QueueView>('pending')
  const [requests, setRequests] = useState<VerificationRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [reviewingId, setReviewingId] = useState<string | null>(null)
  const [reviewNotes, setReviewNotes] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('')
  const [drawerRequest, setDrawerRequest] = useState<VerificationRequest | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      // pending_admin_validation is a client-side filter on validation_origin, not a status
      const serverStatus = statusFilter === 'pending_admin_validation' ? undefined : statusFilter || undefined
      const data =
        view === 'pending'
          ? await listVerificationQueue(serverStatus)
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

  // A notification names one submission, so open it rather than dropping the
  // reviewer on a queue to search — which is the moment they have the least
  // context about which row the mail was for, and gets worse as the queue
  // grows. Runs once the row exists; if the request is not in the current view
  // (already decided, say) nothing happens and the plain queue is shown.
  const focusedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!focusRequestUuid || loading) return
    if (focusedRef.current === focusRequestUuid) return
    if (!requests.some(r => r.uuid === focusRequestUuid)) return
    focusedRef.current = focusRequestUuid
    setExpandedId(focusRequestUuid)
    // Let the expanded body render before scrolling to it.
    requestAnimationFrame(() => {
      document
        .querySelector(`[data-request-uuid="${focusRequestUuid}"]`)
        ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
  }, [focusRequestUuid, loading, requests])

  const handleAction = async (uuid: string, action: 'approved' | 'rejected' | 'in_review' | 'returned') => {
    // Publishing is one decision. Organization visibility and collection
    // membership are curated afterwards on the Catalog tab, where that work
    // already lives, rather than bolted onto the button.
    await updateVerificationStatus(uuid, action, reviewNotes.trim() || undefined)
    setReviewingId(null)
    setReviewNotes('')
    refresh()
  }

  const handleOpen = (req: VerificationRequest) => {
    if (req.item_kind === 'workflow') {
      navigate({
        to: '/',
        search: {
          mode: undefined,
          tab: undefined,
          workflow: req.item_id,
          extraction: undefined,
          automation: undefined,
          kb: undefined,
          project: undefined,
          workflow_share_token: undefined,
        },
      })
    } else if (req.item_uuid) {
      navigate({
        to: '/',
        search: {
          mode: undefined,
          tab: undefined,
          workflow: undefined,
          extraction: req.item_uuid,
          automation: undefined,
          kb: undefined,
          project: undefined,
          workflow_share_token: undefined,
        },
      })
    }
  }

  const filtered = requests.filter(r => {
    // Client-side validation_origin filter (Phase B)
    if (statusFilter === 'pending_admin_validation') {
      if (r.validation_origin !== 'pending_admin_validation') return false
    } else if (view === 'mine' && statusFilter && r.status !== statusFilter) {
      // Client-side status filtering for "mine" view
      return false
    }
    // Search filtering
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return (
        (r.item_name || '').toLowerCase().includes(q) ||
        (r.summary || '').toLowerCase().includes(q) ||
        (r.submitter_name || '').toLowerCase().includes(q) ||
        (r.submitter?.name || '').toLowerCase().includes(q) ||
        (r.submitter?.email || '').toLowerCase().includes(q) ||
        (r.description || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  return (
    <div>
      {/* The bar, stated. Without it each examiner supplies their own, and the
          private standard is always "perfect". */}
      {view === 'pending' && (
        <p className="mb-3 text-xs text-gray-600 border-l-2 border-gray-300 pl-3">
          <span className="font-semibold text-gray-800">The bar:</span> useful to someone here, and honest about what it does.
          The score travels with it and can be low. Send back with a note when a small change would get it there.
        </p>
      )}

      {/* Search + view toggle + status filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search requests..."
            aria-label="Search submissions"
            className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-gray-400"
          />
        </div>
        <div role="group" aria-label="Shared items views" className="flex items-center gap-2">
          <button
            type="button"
            aria-pressed={view === 'pending'}
            onClick={() => setView('pending')}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              view === 'pending'
                ? 'bg-gray-900 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            Requests
          </button>
          <button
            type="button"
            aria-pressed={view === 'mine'}
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
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          {([
            ['', 'All'],
            ['submitted', 'Submitted'],
            ['in_review', 'In Review'],
            ...(view === 'pending' ? [['pending_admin_validation' as StatusFilter, 'Needs validation help'] as [StatusFilter, string]] : []),
            ...(view === 'mine' ? [['returned' as StatusFilter, 'Sent back'] as [StatusFilter, string]] : []),
          ] as [StatusFilter, string][]).map(([val, label]) => (
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
        <div role="status" aria-live="polite" className="text-sm text-gray-500 py-8 text-center">Loading...</div>
      ) : filtered.length === 0 ? (
        <div role="status" aria-live="polite" className="text-sm text-gray-500 py-12 text-center">
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
                data-request-uuid={req.uuid}
                className="border border-gray-200 rounded-lg bg-white"
              >
                <div className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <button
                          type="button"
                          onClick={() => setExpandedId(isExpanded ? null : req.uuid)}
                          aria-expanded={isExpanded}
                          aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
                          className="p-0.5 rounded hover:bg-gray-100 text-gray-400 shrink-0"
                        >
                          {isExpanded ? <ChevronDown className="h-4 w-4" aria-hidden="true" /> : <ChevronRight className="h-4 w-4" aria-hidden="true" />}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleOpen(req)}
                          className="p-0.5 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-600 shrink-0"
                          aria-label="Open item"
                          title="Open item"
                        >
                          <ExternalLink className="h-4 w-4" aria-hidden="true" />
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
                        {req.validation_origin === 'pending_admin_validation' && (
                          <span className="text-xs px-2 py-0.5 rounded border shrink-0 bg-amber-50 text-amber-700 border-amber-200" title="Submitter requested admin help with validation">
                            Needs validation
                          </span>
                        )}
                        {req.examiner_baseline_additions && (
                          <span className="text-xs px-2 py-0.5 rounded border shrink-0 bg-purple-50 text-purple-700 border-purple-200" title="Examiner has added baseline cases">
                            Curated
                          </span>
                        )}
                        {req.claimed_by_user_id && req.claimed_by_user_id !== user?.user_id && (
                          <span className="text-xs px-2 py-0.5 rounded border shrink-0 bg-gray-50 text-gray-600 border-gray-200 inline-flex items-center gap-1" title="Another reviewer is currently working on this">
                            <UserCheck className="h-3 w-3" />
                            In progress
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 ml-9 flex items-center gap-3 flex-wrap">
                        <span>{req.item_kind === 'workflow' ? 'Workflow' : req.item_kind === 'knowledge_base' ? 'Knowledge Base' : 'Extraction'}</span>
                        {req.submitter ? (
                          <AuthorChip author={req.submitter} label="by" />
                        ) : req.submitter_name ? (
                          <span>by {req.submitter_name}</span>
                        ) : null}
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
                                onClick={() => setDrawerRequest(req)}
                                className="px-2 py-1.5 text-xs font-medium rounded-md bg-purple-50 text-purple-700 border border-purple-200 hover:bg-purple-100 inline-flex items-center gap-1"
                                title="Open Validation Workshop"
                              >
                                <Wrench className="h-3 w-3" />
                                Workshop
                              </button>
                              {req.status === 'submitted' && (
                                <button
                                  onClick={() => handleAction(req.uuid, 'in_review')}
                                  className="px-3 py-1.5 text-xs font-medium rounded-md bg-yellow-100 text-yellow-800 border border-yellow-300 hover:bg-yellow-200"
                                  title="Claim this submission and mark it as actively under review"
                                >
                                  Mark In Review
                                </button>
                              )}
                              <button
                                onClick={() => setReviewingId(req.uuid)}
                                className="px-3 py-1.5 text-xs font-medium rounded-md bg-gray-900 text-white hover:bg-gray-800"
                              >
                                Review
                              </button>
                            </>
                          ) : (
                            <div className="flex flex-col gap-2 w-64">
                              <textarea
                                value={reviewNotes}
                                onChange={(e) => setReviewNotes(e.target.value)}
                                placeholder="What would get it there? Shown to the author. (optional)"
                                rows={2}
                                className="text-xs border border-gray-300 rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-gray-400"
                              />
                              {/* Baseline note in reviewer language: what publishing does,
                                  not a warning about a subsystem. Absence is information, not
                                  a reason to hesitate — it can be pinned later from the Catalog tab. */}
                              {(req.validation_snapshot || req.examiner_baseline_additions) ? (
                                <div className="text-[10px] text-gray-500 inline-flex items-center gap-1">
                                  <Pin className="h-3 w-3" />
                                  Accepting pins the {req.examiner_baseline_additions && req.validation_snapshot ? 'merged' : req.examiner_baseline_additions ? 'examiner-curated' : 'submitter\'s'} validation as the baseline monitoring compares against.
                                </div>
                              ) : (
                                <div className="text-[10px] text-gray-500 inline-flex items-center gap-1">
                                  <Pin className="h-3 w-3" />
                                  No validation run yet — the entry won't be monitored for drift until one is pinned. You can pin one later from the Catalog tab.
                                </div>
                              )}
                              {/* Two real outcomes: accept it, or send it back with notes.
                                  Declining outright is rare enough to sit below the row. */}
                              <div className="flex gap-1">
                                <button
                                  onClick={() => handleAction(req.uuid, 'approved')}
                                  className="flex-1 px-2 py-1 text-xs font-medium rounded bg-green-600 text-white hover:bg-green-700"
                                >
                                  Accept
                                </button>
                                <button
                                  onClick={() => handleAction(req.uuid, 'returned')}
                                  className="flex-1 px-2 py-1 text-xs font-medium rounded bg-orange-500 text-white hover:bg-orange-600"
                                >
                                  Send back
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
                              <button
                                type="button"
                                onClick={() => handleAction(req.uuid, 'rejected')}
                                className="self-start text-[11px] text-red-700 hover:underline"
                                title="Close this request without sharing it. Prefer Send back when a revision could get it there."
                              >
                                Decline instead
                              </button>
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
                      {req.validation_snapshot && (() => {
                        const snapshot = req.validation_snapshot as Record<string, unknown>
                        const aggregateAccuracy =
                          typeof snapshot.aggregate_accuracy === 'number' ? snapshot.aggregate_accuracy : null
                        const aggregateConsistency =
                          typeof snapshot.aggregate_consistency === 'number' ? snapshot.aggregate_consistency : null
                        const grade = typeof snapshot.grade === 'string' ? snapshot.grade : null
                        const summary = typeof snapshot.summary === 'string' ? snapshot.summary : null
                        const isSearchSet = req.item_kind === 'search_set'

                        return (
                          <DetailSection label="Validation Results">
                            {isSearchSet ? (
                              <div className="space-y-1">
                                {aggregateAccuracy != null && (
                                  <div className="text-xs">Accuracy: <span className="font-medium">{Math.round(aggregateAccuracy * 100)}%</span></div>
                                )}
                                {aggregateConsistency != null && (
                                  <div className="text-xs">Consistency: <span className="font-medium">{Math.round(aggregateConsistency * 100)}%</span></div>
                                )}
                              </div>
                            ) : (
                              <div className="space-y-1">
                                {grade && (
                                  <div className="text-xs">Grade: <span className="font-semibold">{grade}</span></div>
                                )}
                                {summary && (
                                  <div className="text-xs">{summary}</div>
                                )}
                              </div>
                            )}
                            {req.validation_score != null && (
                              <div className="text-xs mt-1">Quality Score: <span className="font-medium">{Math.round(req.validation_score)}%</span> ({req.validation_tier || 'unrated'})</div>
                            )}
                          </DetailSection>
                        )
                      })()}
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

      {drawerRequest && user?.user_id && (
        <ExaminerValidationDrawer
          request={drawerRequest}
          currentUserId={user.user_id}
          onClose={() => setDrawerRequest(null)}
          onSaved={() => refresh()}
        />
      )}
    </div>
  )
}
