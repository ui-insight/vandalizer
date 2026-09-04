import { useCallback } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Award,
  ClipboardCheck,
  MessageSquare,
  Workflow,
  ListChecks,
  Trash2,
  PanelLeftClose,
  PanelLeftOpen,
  Zap,
  Clock,
  Settings,
  AlertTriangle,
  CircleMinus,
  CircleCheck,
  SquarePen,
} from 'lucide-react'
import { useActivities } from '../../hooks/useActivities'
import { useMyReviewCount } from '../../hooks/useMyReviewCount'
import { deleteActivity } from '../../api/activity'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useToast } from '../../contexts/ToastContext'
import { useConfirm } from '../shared/useConfirm'
import { useCertificationPanel } from '../../contexts/CertificationPanelContext'
import { LEVEL_CONFIG } from '../certification/constants'
import { cn } from '../../lib/cn'
import type { ActivityEvent } from '../../types/chat'

function activityIcon(type: ActivityEvent['type']) {
  switch (type) {
    case 'conversation':
      return MessageSquare
    case 'workflow_run':
      return Workflow
    case 'search_set_run':
      return ListChecks
    default:
      return MessageSquare
  }
}

function StatusIcon({ status }: { status: ActivityEvent['status'] }) {
  switch (status) {
    case 'queued':
      return <Clock className="h-3 w-3" />
    case 'running':
      return <Settings className="h-3 w-3 animate-spin" />
    case 'failed':
      return <AlertTriangle className="h-3 w-3" />
    case 'canceled':
      return <CircleMinus className="h-3 w-3" />
    case 'completed':
      return <CircleCheck className="h-3 w-3" />
    default:
      return null
  }
}

function statusMetaClass(status: ActivityEvent['status']) {
  switch (status) {
    case 'completed':
      return 'text-[#1a7f37]'
    case 'failed':
      return 'text-[#b3261e]'
    default:
      return 'text-[#0050d7]'
  }
}

// A workflow run parked on an approval gate carries the pending review's uuid
// in meta_summary. The status stays "running" (ActivityStatus has no paused
// member), so this marker is what separates "waiting on a person" from
// "waiting on a worker" everywhere in the rail.
export function pendingReviewUuid(activity: ActivityEvent): string | null {
  const uuid = (activity.meta_summary as { pending_review_uuid?: unknown } | undefined)
    ?.pending_review_uuid
  return typeof uuid === 'string' && uuid ? uuid : null
}

/** The review a row is *currently* waiting on, or null.
 *
 * The marker records that a run paused on a review; it does not record that it
 * still is. Several exits leave it behind — cancelling rewrites the activity
 * without touching meta_summary, and a failure stamped after the marker keeps
 * it — so reading the marker alone makes a terminal row render as awaiting
 * approval, with a clock, a live link to a review nobody can act on, and its
 * real error text suppressed. Only a live row can be waiting on anyone.
 */
export function activeReviewUuid(activity: ActivityEvent): string | null {
  const live = activity.status === 'running' || activity.status === 'queued'
  return live ? pendingReviewUuid(activity) : null
}

// Threshold mirrors SystemConfig.retention_config.activity_stale_threshold_minutes
// (default 30 min) so the UI flips to "timed out" the instant the threshold
// passes, instead of waiting for the next backend reap cycle.
export function isStale(activity: ActivityEvent, thresholdMinutes: number): boolean {
  if (activity.status !== 'running' && activity.status !== 'queued') return false
  // A run waiting on a reviewer reports no progress by design — it is stalled
  // only in the sense that a person has not acted, which is not a timeout.
  if (pendingReviewUuid(activity)) return false
  const ts = activity.last_updated_at || activity.started_at
  if (!ts) return false
  const age = Date.now() - new Date(ts).getTime()
  return age > thresholdMinutes * 60 * 1000
}

export function ActivityRail() {
  const { railDocked, toggleRailDocked, setActiveRightTab, setLoadConversationId, triggerNewChat, openWorkflow, openExtraction, closeWorkflow, closeExtraction, closeAutomation, activitySignal, currentConversationUuid } = useWorkspace()
  const { activities, refresh, freshTitleIds, markTitleShimmered, staleThresholdMinutes } = useActivities(activitySignal)
  const { count: pendingReviews } = useMyReviewCount()
  const navigate = useNavigate()
  const { toast } = useToast()
  const { togglePanel, progress } = useCertificationPanel()
  const confirm = useConfirm()

  const certLevel = progress?.level || 'novice'
  const certConfig = LEVEL_CONFIG[certLevel] || LEVEL_CONFIG.novice
  const certXp = progress?.total_xp || 0
  const certCertified = !!progress?.certified
  const certStarted = certXp > 0

  const handleDelete = useCallback(
    async (e: React.MouseEvent, id: string) => {
      e.stopPropagation()
      const activity = activities.find(a => a.id === id)
      const label = activity?.type === 'conversation'
        ? 'this conversation'
        : activity?.type === 'workflow_run'
          ? 'this workflow run'
          : activity?.type === 'search_set_run'
            ? 'this extraction run'
            : 'this activity'
      const ok = await confirm({
        title: 'Delete from activity?',
        message: `Are you sure you want to delete ${label} from your activity history? This cannot be undone.`,
        confirmLabel: 'Delete',
        destructive: true,
      })
      if (!ok) return
      try {
        await deleteActivity(id)
        // If the deleted activity is the conversation currently open in
        // the chat panel, reset the panel so its messages don't linger
        // after the backing conversation is gone.
        if (
          activity?.type === 'conversation' &&
          activity.conversation_id &&
          activity.conversation_id === currentConversationUuid
        ) {
          triggerNewChat()
        }
      } catch (err) {
        toast(err instanceof Error ? err.message : 'Failed to delete activity', 'error')
      }
      refresh()
    },
    [refresh, toast, activities, confirm, currentConversationUuid, triggerNewChat],
  )

  const handleClick = useCallback(
    (activity: ActivityEvent) => {
      if (activity.type === 'conversation' && activity.conversation_id) {
        closeWorkflow()
        closeExtraction()
        closeAutomation()
        setActiveRightTab('assistant')
        setLoadConversationId(activity.conversation_id)
      } else if (activity.type === 'workflow_run' && pendingReviewUuid(activity)) {
        // The run is frozen at the gate — there is nothing to see in the editor
        // that the review does not show, and the review is the only thing that
        // moves it forward.
        navigate({ to: '/reviews/$uuid', params: { uuid: pendingReviewUuid(activity)! } })
      } else if (activity.type === 'workflow_run' && activity.workflow_id) {
        openWorkflow(activity.workflow_id, activity.workflow_session_id ?? undefined)
      } else if (activity.type === 'search_set_run' && activity.search_set_uuid) {
        // Restore the extraction results from the activity snapshot so the
        // editor re-opens with values rather than a blank slate.
        const normalized = activity.result_snapshot?.normalized as Record<string, string> | undefined
        const initialResults = normalized && typeof normalized === 'object' && Object.keys(normalized).length > 0
          ? Object.fromEntries(Object.entries(normalized).map(([k, v]) => [k, v === null ? 'N/A' : String(v)]))
          : undefined
        const snapSources = activity.result_snapshot?.sources as import('../../api/extractions').ExtractionSourceMap | undefined
        const initialSources = snapSources && typeof snapSources === 'object' && Object.keys(snapSources).length > 0
          ? snapSources
          : undefined
        // The run's cross-field verdict is in the same snapshot. Restoring
        // values without it re-opens a run that failed a budget rule looking
        // exactly like one that passed.
        type CFR = import('../../api/extractions').CrossFieldRunReport
        type DW = import('../../api/extractions').DocumentWarning
        const snap = activity.result_snapshot as {
          cross_field?: CFR | null
          cross_field_sets?: (CFR | null)[]
          document_warnings?: DW[]
        } | undefined
        const snapCrossField = snap?.cross_field_sets
          ?? (snap?.cross_field ? [snap.cross_field] : undefined)
        const initialCrossField = snapCrossField?.length ? snapCrossField : undefined
        // Same reasoning: values restored without the caveats attached to
        // them re-open looking like values from documents read whole.
        const initialWarnings = snap?.document_warnings?.length
          ? snap.document_warnings
          : undefined
        openExtraction(
          activity.search_set_uuid, initialResults, initialSources,
          initialCrossField, initialWarnings,
        )
      }
    },
    [setActiveRightTab, setLoadConversationId, openWorkflow, openExtraction, closeWorkflow, closeExtraction, closeAutomation, navigate],
  )

  const isRunning = (status: ActivityEvent['status']) =>
    status === 'running' || status === 'queued'

  return (
    <aside
      className="flex h-full flex-col border-l border-[#d8d8d8] bg-panel-bg"
    >
      {/* Header */}
      <div className="border-b border-[#ddd]" style={{ padding: '17px 12px' }}>
        <div className="flex items-center justify-between gap-2">
          {!railDocked && (
            <div className="flex items-center gap-2">
              <Zap className="h-3.5 w-3.5" />
              <span className="text-sm font-bold">Activity</span>
            </div>
          )}
          <button
            onClick={toggleRailDocked}
            className="flex items-center justify-center rounded p-1 text-[#333] hover:bg-[#e0e0e0] hover:text-[#111] transition-colors ml-auto"
            title={railDocked ? 'Expand' : 'Collapse'}
          >
            {railDocked ? <PanelLeftOpen className="h-3.5 w-3.5" /> : <PanelLeftClose className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Activity list — flex-1 so cert badge footer stays at bottom */}
      <div className="flex-1 overflow-y-auto hide-scrollbar p-2">
        <div className="flex flex-col gap-1">
          {/* New chat button - matches Flask _app_rail.html first item */}
          <div
            onClick={triggerNewChat}
            className={cn(
              'flex items-center gap-2 rounded-lg cursor-pointer p-2',
              'hover:bg-[#f0f2f5] hover:shadow-[0_1px_3px_rgb(15_23_42/0.12)]',
              'transition-[background-color,box-shadow] duration-200',
              railDocked ? 'justify-center' : '',
            )}
          >
            <div className="shrink-0 w-4 text-center text-[#333]">
              <SquarePen className="h-4 w-4" />
            </div>
            {!railDocked && (
              <div className="text-[11px] leading-[1.4] text-[#111]">New chat</div>
            )}
          </div>

          {/* Pending reviews — only when something is actually waiting, so the
              rail stays quiet for the many users who never review anything.
              The always-present entry point is the account menu. */}
          {pendingReviews > 0 && (
            <div
              onClick={() => navigate({ to: '/reviews' })}
              title={`${pendingReviews} approval${pendingReviews === 1 ? '' : 's'} waiting on you`}
              className={cn(
                'flex items-center gap-2 rounded-lg cursor-pointer p-2',
                'hover:bg-[#f0f2f5] hover:shadow-[0_1px_3px_rgb(15_23_42/0.12)]',
                'transition-[background-color,box-shadow] duration-200',
                railDocked ? 'justify-center' : '',
              )}
            >
              <div className="relative shrink-0 w-4 text-center text-[#806600]">
                <ClipboardCheck className="h-4 w-4" />
                {railDocked && (
                  <span
                    className="absolute -right-1 -top-1 h-[7px] w-[7px] rounded-full"
                    style={{ backgroundColor: 'var(--highlight-color, #eab308)' }}
                  />
                )}
              </div>
              {!railDocked && (
                <>
                  <div className="min-w-0 flex-1 text-[11px] leading-[1.4] text-[#111]">
                    Reviews
                  </div>
                  <span
                    className="shrink-0 rounded-full px-1.5 text-[10px] font-semibold text-[#111]"
                    style={{ backgroundColor: 'var(--highlight-color, #eab308)' }}
                  >
                    {pendingReviews}
                  </span>
                </>
              )}
            </div>
          )}
          <div className="h-[5px]" />

          {activities.map((activity) => {
            const awaitingReview = activeReviewUuid(activity)
            const Icon = awaitingReview ? ClipboardCheck : activityIcon(activity.type)
            const stale = isStale(activity, staleThresholdMinutes)
            // A paused run is not "running": the shimmer would claim work is
            // happening while it sits on a reviewer, possibly for days.
            const running = isRunning(activity.status) && !stale && !awaitingReview
            const titleFresh = freshTitleIds.has(activity.id)
            // "queued" renders the clock — the honest icon for a run parked on
            // a person. The spinner would imply a worker is still churning.
            const effectiveStatus: ActivityEvent['status'] =
              stale ? 'failed' : awaitingReview ? 'queued' : activity.status
            const staleTooltip = stale
              ? `Timed out — no progress for over ${staleThresholdMinutes} minutes.`
              : undefined
            const rowTooltip = awaitingReview
              ? 'Paused — waiting on your approval. Opens the review.'
              : staleTooltip
            const aiTitleReady = (activity.meta_summary as { description_generated?: boolean } | undefined)
              ?.description_generated === true
            // Once the activity is done but the title generator hasn't
            // finished yet, show a shimmering placeholder instead of the
            // raw working title — signals "we're cooking up a name".
            // Cap to ~2 min after completion so a silently failed Celery
            // task can't leave the row stuck on the placeholder.
            const finishedAt = activity.finished_at ? new Date(activity.finished_at).getTime() : 0
            const ageMs = finishedAt ? Date.now() - finishedAt : 0
            const awaitingTitle =
              activity.status === 'completed' && !aiTitleReady && ageMs < 120000
            const displayTitle = awaitingTitle
              ? 'Generating title…'
              : (activity.title || activity.type)

            return (
              <div
                key={activity.id}
                onClick={() => handleClick(activity)}
                title={rowTooltip}
                className={cn(
                  'rail-shimmer-running group relative flex items-center gap-2 rounded-lg cursor-pointer',
                  'transition-[background-color,box-shadow] duration-200',
                  railDocked ? 'justify-center p-2' : 'p-2',
                  running
                    ? 'text-white'
                    : 'hover:bg-[#f0f2f5] hover:shadow-[0_1px_3px_rgb(15_23_42/0.12)]',
                )}
                style={
                  running
                    ? {
                        background: `linear-gradient(90deg, var(--highlight-complement, #6a11cb) 0%, var(--highlight-color, #f1b300) 50%, var(--highlight-complement, #6a11cb) 100%)`,
                        backgroundSize: '200% 100%',
                        animation: 'rail-shimmer 8s linear infinite',
                      }
                    : undefined
                }
              >
                {/* Type icon */}
                <div className={cn(
                  'relative shrink-0 w-4 text-center',
                  running ? 'text-white' : awaitingReview ? 'text-[#806600]' : railDocked ? 'text-[#999]' : 'text-[#333]',
                )}>
                  <Icon className="h-4 w-4" />
                  {awaitingReview && railDocked && (
                    <span
                      className="absolute -right-1 -top-1 h-[7px] w-[7px] rounded-full"
                      style={{ backgroundColor: 'var(--highlight-color, #eab308)' }}
                    />
                  )}
                </div>

                {!railDocked && (
                  <>
                    {/* Title + status — clamp to 2 lines so AI titles can
                        breathe without blowing out the rail width. */}
                    <div className="min-w-0 flex-1">
                      <div
                        className={cn(
                          'text-[11px] leading-[1.4] break-words line-clamp-2',
                          running ? 'text-white' : 'text-[#111]',
                          // Shimmer when the AI title just arrived (one-shot)
                          // or while we're waiting for it to generate (loops
                          // via title-shimmer-loop).
                          titleFresh && !running ? 'title-shimmer' : '',
                          awaitingTitle ? 'title-shimmer-loop' : '',
                        )}
                        onAnimationEnd={titleFresh ? () => markTitleShimmered(activity.id) : undefined}
                      >
                        {displayTitle}
                      </div>
                      {awaitingReview && (
                        <div className="text-[10px] leading-[1.4] font-semibold text-[#806600]">
                          Awaiting approval →
                        </div>
                      )}
                    </div>

                    {/* Status icon */}
                    <div
                      className={cn('shrink-0 opacity-90', running ? 'text-white' : statusMetaClass(effectiveStatus))}
                      title={rowTooltip ?? (activity.status === 'failed' && activity.error ? activity.error : undefined)}
                    >
                      <StatusIcon status={effectiveStatus} />
                    </div>

                    {/* Delete button - always visible for failed/canceled/stale, hover for others */}
                    <button
                      onClick={(e) => handleDelete(e, activity.id)}
                      className={cn(
                        'absolute right-1 top-1/2 -translate-y-1/2 z-[1]',
                        'flex items-center justify-center',
                        'rounded p-1',
                        'transition-[opacity,color,background-color] duration-200',
                        stale || activity.status === 'failed' || activity.status === 'canceled'
                          ? 'opacity-70 pointer-events-auto hover:opacity-100'
                          : 'opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto',
                        'text-[#7a7f87] hover:text-[#444]',
                        running
                          ? 'bg-white/30 backdrop-blur-sm hover:bg-white/50'
                          : 'bg-white/90 backdrop-blur-sm shadow-[0_1px_3px_rgba(0,0,0,0.1)] hover:bg-white/95',
                      )}
                      title={staleTooltip
                        ? `Delete - ${staleTooltip}`
                        : activity.status === 'failed' && activity.error
                          ? `Delete - Error: ${activity.error}`
                          : 'Delete'}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Certification badge footer */}
      <div className="border-t border-[#ddd] p-2 shrink-0 flex justify-center">
        <div
          onClick={togglePanel}
          title={certCertified ? 'Vandal Workflow Architect' : certStarted ? `${certConfig.label} · ${certXp} XP` : 'Get Certified'}
          className="flex items-center gap-2 cursor-pointer transition-all hover:shadow-md active:scale-95"
          style={{
            borderRadius: 'var(--ui-radius, 12px)',
            padding: railDocked ? '6px 10px' : '6px 12px',
            ...(certCertified
              ? { background: 'linear-gradient(135deg, #191919, #2d2d2d)', border: '1px solid #444', boxShadow: '0 2px 8px rgba(234,179,8,0.2)' }
              : { background: '#fff', border: '1px solid #e5e7eb', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }),
          }}
        >
          <Award
            className="h-3.5 w-3.5 shrink-0"
            style={{ color: certCertified ? '#eab308' : certStarted ? certConfig.color : 'var(--highlight-on-light, #806600)' }}
          />
          {!railDocked && (
            certCertified ? (
              <span className="text-[11px] font-semibold text-yellow-400 title-shimmer">
                Vandal Workflow Architect
              </span>
            ) : certStarted ? (
              <>
                <span className="text-[11px] font-semibold text-[#111]">{certConfig.label}</span>
                <span className="text-[10px] text-[#999]">{certXp} XP</span>
              </>
            ) : (
              <span className="text-[11px] font-semibold text-[#444]">Get Certified</span>
            )
          )}
        </div>
      </div>
    </aside>
  )
}
