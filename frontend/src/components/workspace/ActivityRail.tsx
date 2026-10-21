import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  Pencil,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { useActivities } from '../../hooks/useActivities'
import { useMyReviewCount } from '../../hooks/useMyReviewCount'
import { deleteActivity, renameActivity } from '../../api/activity'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { pendingReviewUuid, useOpenActivity } from '../../hooks/useOpenActivity'
import { useToast } from '../../contexts/ToastContext'
import { useConfirm } from '../shared/useConfirm'
import { useCertificationPanel } from '../../contexts/CertificationPanelContext'
import { LEVEL_CONFIG } from '../certification/constants'
import { cn } from '../../lib/cn'
import type { ActivityEvent } from '../../types/chat'
import {
  groupActivities, runDocumentLabel, runKindLabel, runName, runTimeLabel, shortError,
  type ChatGroup,
} from './activityGroups'

export { pendingReviewUuid }

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
      return 'text-[#166534]'
    case 'failed':
      return 'text-[#b3261e]'
    default:
      return 'text-[#0050d7]'
  }
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

export function ActivityRail({ forceExpanded = false, forceDocked = false, onExpand, onNavigate }: { forceExpanded?: boolean; forceDocked?: boolean; onExpand?: () => void; onNavigate?: () => void }) {
  const { railDocked, toggleRailDocked, triggerNewChat, focusChat, activitySignal, currentConversationUuid, openWorkflowId, openExtractionId } = useWorkspace()
  const { activities, loading, error, refresh, staleThresholdMinutes } = useActivities(activitySignal)
  const { count: pendingReviews } = useMyReviewCount()
  const navigate = useNavigate()
  const { toast } = useToast()
  const { openInChat, progress, course } = useCertificationPanel()
  // An outcome-based course awards its own credential; the legacy course keeps its title.
  const certTitle = course?.credential_scope && course.course_title ? course.course_title : 'Vandal Workflow Architect'
  const confirm = useConfirm()
  const deletePending = useRef(false)
  const [deleting, setDeleting] = useState(false)
  // The mobile drawer always needs its labels; a collapsed rail inside a
  // full-width drawer would waste space and make the activity list opaque.
  const visualDocked = forceExpanded ? false : forceDocked || railDocked

  const certLevel = progress?.level || 'novice'
  const certConfig = LEVEL_CONFIG[certLevel] || LEVEL_CONFIG.novice
  const certXp = progress?.total_xp || 0
  const certCertified = !!progress?.certified
  const certStarted = certXp > 0

  const handleDelete = useCallback(
    async (e: React.MouseEvent, id: string) => {
      e.stopPropagation()
      if (deletePending.current) return
      deletePending.current = true
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
      if (!ok) { deletePending.current = false; return }
      setDeleting(true)
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
      } finally {
        deletePending.current = false
        setDeleting(false)
      }
      refresh()
    },
    [refresh, toast, activities, confirm, currentConversationUuid, triggerNewChat],
  )

  // The chat being renamed in place, and the name typed so far.
  const [renaming, setRenaming] = useState<{ id: string; value: string; original: string } | null>(null)
  const renameSaving = useRef(false)

  const saveRename = useCallback(async () => {
    if (!renaming || renameSaving.current) return
    const value = renaming.value.trim()
    if (!value || value === renaming.original) { setRenaming(null); return }
    renameSaving.current = true
    try {
      await renameActivity(renaming.id, value)
      setRenaming(null)
      refresh()
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Could not rename this chat', 'error')
    } finally {
      renameSaving.current = false
    }
  }, [renaming, refresh, toast])

  // Chats the user opened or closed; the chat in use starts open.
  const [chatOpen, setChatOpen] = useState<Record<string, boolean>>({})
  const isChatExpanded = (group: ChatGroup) =>
    chatOpen[group.chat.id] ?? (!!currentConversationUuid && group.chat.conversation_id === currentConversationUuid)
  const [otherRunsOpen, setOtherRunsOpen] = useState(true)
  const [errorOpen, setErrorOpen] = useState<Record<string, boolean>>({})
  const { chats, otherRuns } = useMemo(
    () => groupActivities(activities, currentConversationUuid),
    [activities, currentConversationUuid],
  )

  const { openActivity: handleClick } = useOpenActivity()
  const [returnActivity, setReturnActivity] = useState(() => {
    try { return sessionStorage.getItem('activity-return-id') } catch { return null }
  })
  const railRef = useRef<HTMLElement>(null)
  const previousTool = useRef(openWorkflowId || openExtractionId)
  useEffect(() => {
    const tool = openWorkflowId || openExtractionId
    if (previousTool.current && !tool) {
      railRef.current?.querySelector<HTMLButtonElement>('[data-activity-return="true"]')?.focus({ preventScroll: true })
    }
    previousTool.current = tool
  }, [openWorkflowId, openExtractionId])

  const renderEntry = (activity: ActivityEvent, group?: ChatGroup, nested = false) => {
    const awaitingReview = activeReviewUuid(activity)
    const Icon = awaitingReview ? ClipboardCheck : activityIcon(activity.type)
    const stale = isStale(activity, staleThresholdMinutes)
    // A paused run is not "running": the shimmer would claim work is
    // happening while it sits on a reviewer, possibly for days.
    // "queued" renders the clock — the honest icon for a run parked on
    // a person. The spinner would imply a worker is still churning.
    const effectiveStatus: ActivityEvent['status'] =
      stale ? 'failed' : awaitingReview ? 'queued' : activity.status
    const staleTooltip = stale
      ? `Timed out: no progress for over ${staleThresholdMinutes} minutes.`
      : undefined
    const rowTooltip = awaitingReview
      ? 'Paused — waiting on your approval. Opens the review.'
      : staleTooltip
    const isChat = activity.type === 'conversation'
    const aiTitleReady = (activity.meta_summary as { description_generated?: boolean } | undefined)
      ?.description_generated === true
    // Once a chat is done but the title generator hasn't finished yet, show a
    // shimmering placeholder instead of the raw working title. Capped to ~2
    // min after completion so a silently failed Celery task can't leave the
    // row stuck on the placeholder. Runs keep their template's name.
    const finishedAt = activity.finished_at ? new Date(activity.finished_at).getTime() : 0
    const ageMs = finishedAt ? Date.now() - finishedAt : 0
    const awaitingTitle =
      isChat && activity.status === 'completed' && !aiTitleReady && ageMs < 120000
    const displayTitle = awaitingTitle
      ? 'Generating title…'
      : isChat ? (activity.title || activity.type) : runName(activity)

    const statusLabel = stale ? 'Timed out' : awaitingReview ? 'Awaiting approval' : {
      queued: 'Queued', running: 'Running', completed: 'Completed', failed: 'Failed', canceled: 'Cancelled',
    }[activity.status]
    const failureReason = staleTooltip || (activity.status === 'failed' ? activity.error : '')
    // What a run read and when, so two runs of one template can be told apart.
    const runDetail = isChat ? '' : [
      runKindLabel(activity), runDocumentLabel(activity), runTimeLabel(activity.started_at),
    ].filter(Boolean).join(' · ')
    const runCount = group?.runs.length ?? 0
    const chatExpanded = group ? isChatExpanded(group) : false
    if (renaming?.id === activity.id && !visualDocked) {
      return (
        <div key={activity.id} className="activity-entry">
          <form
            className="activity-entry__rename-form"
            onSubmit={e => { e.preventDefault(); void saveRename() }}
          >
            <MessageSquare className="h-4 w-4 shrink-0" aria-hidden="true" />
            <input
              autoFocus
              aria-label="Chat name"
              maxLength={120}
              value={renaming.value}
              onChange={e => setRenaming({ ...renaming, value: e.target.value })}
              onFocus={e => e.currentTarget.select()}
              onBlur={() => void saveRename()}
              onKeyDown={e => { if (e.key === 'Escape') { e.preventDefault(); setRenaming(null) } }}
              className="activity-entry__rename-input"
            />
          </form>
        </div>
      )
    }
    return (
      <div key={activity.id}>
        <div className={cn('activity-entry', nested && 'activity-entry--nested')}>
          {!visualDocked && group && runCount > 0 && (
            <button
              type="button"
              aria-expanded={chatExpanded}
              aria-label={`${chatExpanded ? 'Hide' : 'Show'} ${runCount} run${runCount === 1 ? '' : 's'} from ${displayTitle}`}
              onClick={() => setChatOpen(prev => ({ ...prev, [activity.id]: !chatExpanded }))}
              className="activity-entry__toggle"
            >
              {chatExpanded ? <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />}
            </button>
          )}
          <button
            type="button"
            aria-label={`Open ${isChat ? '' : `${runKindLabel(activity)} `}${displayTitle}: ${statusLabel}`}
            data-activity-return={returnActivity === activity.id || undefined}
            onClick={() => {
              setReturnActivity(activity.id)
              try { sessionStorage.setItem('activity-return-id', activity.id) } catch { /* Storage can be unavailable. */ }
              onNavigate?.(); handleClick(activity)
            }}
            title={rowTooltip || `${displayTitle} — ${statusLabel}`}
            className={cn('activity-entry__open', visualDocked && 'activity-entry__open--compact', nested && 'activity-entry__open--nested')}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            {!visualDocked && (
              <span className="min-w-0 flex-1">
                <span className={cn('block text-xs leading-[1.4] break-words', nested ? 'line-clamp-1' : 'line-clamp-2')}>{displayTitle}</span>
                <span className={cn('flex items-center gap-1 mt-1 text-xs font-semibold', statusMetaClass(effectiveStatus))}>
                  <StatusIcon status={effectiveStatus} />{statusLabel}
                  {runCount > 0 && <span className="font-normal text-[#59616b]">· {runCount} run{runCount === 1 ? '' : 's'}</span>}
                </span>
                {runDetail && <span className="block truncate text-xs mt-0.5 text-[#59616b]">{runDetail}</span>}
                {failureReason && <span className="block truncate text-xs mt-0.5 text-[#59616b]">{shortError(failureReason)}</span>}
              </span>
            )}
          </button>
          {!visualDocked && isChat && (
            <button
              type="button"
              aria-label={`Rename chat: ${displayTitle}`}
              onClick={e => {
                e.stopPropagation()
                const current = activity.title || ''
                setRenaming({ id: activity.id, value: current, original: current })
              }}
              className="activity-entry__rename"
              title="Rename chat"
            ><Pencil className="h-4 w-4" aria-hidden="true" /></button>
          )}
          {!visualDocked && (
            <button
              type="button"
              disabled={deleting}
              aria-label={`Delete activity: ${displayTitle}`}
              onClick={e => handleDelete(e, activity.id)}
              className="activity-entry__delete"
              title="Delete activity"
            ><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
          )}
        </div>
        {!visualDocked && failureReason && (
          <div className={cn('activity-entry__error', nested && 'activity-entry__error--nested')}>
            <button
              type="button"
              aria-expanded={!!errorOpen[activity.id]}
              onClick={() => setErrorOpen(prev => ({ ...prev, [activity.id]: !prev[activity.id] }))}
              className="activity-entry__error-toggle"
            >{errorOpen[activity.id] ? 'Hide details' : 'Details'}</button>
            {errorOpen[activity.id] && <p className="activity-entry__error-text">{failureReason}</p>}
          </div>
        )}
      </div>
    )
  }

  return (
    <aside
      ref={railRef}
      aria-label="Activity"
      className="flex h-full flex-col border-l border-[#d8d8d8] bg-panel-bg"
    >
      {/* Header */}
      <div className="border-b border-[#ddd]" style={{ padding: "17px var(--workspace-space-12)" }}>
        <div className="flex items-center justify-between gap-2">
          {!visualDocked && (
            <div className="flex items-center gap-2">
              <Zap className="h-3.5 w-3.5" />
              <span className="text-sm font-bold">Activity</span>
            </div>
          )}
          <button
            onClick={forceDocked && onExpand ? onExpand : toggleRailDocked}
            className={cn(
              'flex items-center justify-center rounded p-1 text-[#333] hover:bg-[#e0e0e0] hover:text-[#111] transition-colors ml-auto',
              forceExpanded && 'hidden',
            )}
            title={visualDocked ? 'Expand' : 'Collapse'}
            aria-label={visualDocked ? 'Expand activity' : 'Collapse activity'}
          >
            {visualDocked ? <PanelLeftOpen className="h-3.5 w-3.5" /> : <PanelLeftClose className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Activity list — flex-1 so cert badge footer stays at bottom */}
      <div className="flex-1 overflow-y-auto hide-scrollbar p-2">
        <div className="flex flex-col gap-1">
          {/* New chat button - matches Flask _app_rail.html first item */}
          <button
            type="button"
            aria-label="New chat"
            title={visualDocked ? 'New chat' : undefined}
            onClick={() => { onNavigate?.(); triggerNewChat(); focusChat() }}
            className={cn(
              'flex items-center gap-2 rounded-lg cursor-pointer p-2',
              'hover:bg-[#f0f2f5] hover:shadow-[0_1px_3px_rgb(15_23_42/0.12)]',
              'transition-[background-color,box-shadow] duration-200',
              visualDocked ? 'justify-center' : '',
            )}
          >
            <div className="shrink-0 w-4 text-center text-[#333]">
              <SquarePen className="h-4 w-4" />
            </div>
            {!visualDocked && (
              <div className="text-xs leading-[1.4] text-[#111]">New chat</div>
            )}
          </button>

          {/* Pending reviews — only when something is actually waiting, so the
              rail stays quiet for the many users who never review anything.
              The always-present entry point is the account menu. */}
          {pendingReviews > 0 && (
            <button type="button" aria-label={`${pendingReviews} reviews waiting on you`}
              onClick={() => { onNavigate?.(); navigate({ to: '/reviews' }) }}
              title={`${pendingReviews} approval${pendingReviews === 1 ? '' : 's'} waiting on you`}
              className={cn(
                'flex items-center gap-2 rounded-lg cursor-pointer p-2',
                'hover:bg-[#f0f2f5] hover:shadow-[0_1px_3px_rgb(15_23_42/0.12)]',
                'transition-[background-color,box-shadow] duration-200',
                visualDocked ? 'justify-center' : '',
              )}
            >
              <div className="relative shrink-0 w-4 text-center text-[#806600]">
                <ClipboardCheck className="h-4 w-4" />
                {visualDocked && (
                  <span
                    className="absolute -right-1 -top-1 h-[7px] w-[7px] rounded-full"
                    style={{ backgroundColor: 'var(--highlight-color, #eab308)' }}
                  />
                )}
              </div>
              {!visualDocked && (
                <>
                  <div className="min-w-0 flex-1 text-xs leading-[1.4] text-[#111]">
                    Reviews
                  </div>
                  <span
                    className="shrink-0 rounded-full px-1.5 text-xs font-semibold text-[#111]"
                    style={{ backgroundColor: 'var(--highlight-color, #eab308)' }}
                  >
                    {pendingReviews}
                  </span>
                </>
              )}
            </button>
          )}
          <div className="h-[5px]" />
          {loading && activities.length === 0 && <p role="status" className="px-2 text-xs text-[#59616b]">Loading activity…</p>}
          {error && <div role="alert" className="px-2 text-xs text-red-800">
            {!visualDocked && <p>{error} {activities.length > 0 ? 'Showing the last loaded activity.' : ''}</p>}
            <button type="button" aria-label="Retry activity" disabled={loading} className="underline" onClick={() => void refresh()}>{visualDocked ? 'Retry' : 'Retry activity'}</button>
          </div>}
          {!loading && !error && activities.length === 0 && !visualDocked && <p className="px-2 text-xs text-[#59616b]">No activity yet. Start a conversation or run a tool to see it here.</p>}


          {!visualDocked && chats.map(group => {
            const expanded = !visualDocked && group.runs.length > 0 && isChatExpanded(group)
            return (
              <div key={group.chat.id}>
                {renderEntry(group.chat, group)}
                {expanded && (
                  <div role="group" aria-label={`Runs from ${group.chat.title || 'this chat'}`} className="activity-runs">
                    {group.runs.map(run => renderEntry(run, undefined, true))}
                  </div>
                )}
              </div>
            )
          })}

          {otherRuns.length > 0 && !visualDocked && (
            <button
              type="button"
              aria-expanded={otherRunsOpen}
              onClick={() => setOtherRunsOpen(open => !open)}
              className="activity-section"
              title="Runs started from the editors, automations or the API"
            >
              {otherRunsOpen ? <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />}
              <span className="flex-1">Other runs</span>
              <span className="activity-count">{otherRuns.length}</span>
            </button>
          )}
          {!visualDocked && otherRunsOpen && otherRuns.map(run => renderEntry(run))}
        </div>
      </div>

      {/* Certification badge footer */}
      <div className="border-t border-[#ddd] p-2 shrink-0 flex justify-center">
        <button
          type="button"
          aria-label="Open certification in chat"
          onClick={() => { onNavigate?.(); openInChat() }}
          title={certCertified ? certTitle : certStarted ? `${certConfig.label} · ${certXp} XP` : 'Get Certified'}
          className="flex items-center gap-2 cursor-pointer transition-all hover:shadow-md active:scale-95"
          style={{
            borderRadius: 'var(--ui-radius, 12px)',
            padding: visualDocked ? '6px 10px' : '6px 12px',
            ...(certCertified
              ? { background: 'linear-gradient(135deg, #191919, #2d2d2d)', border: '1px solid #444', boxShadow: '0 2px 8px rgba(234,179,8,0.2)' }
              : { background: '#fff', border: "1px solid var(--workspace-border)", boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }),
          }}
        >
          <Award
            className="h-3.5 w-3.5 shrink-0"
            style={{ color: certCertified ? '#eab308' : certStarted ? certConfig.color : 'var(--highlight-on-light, #806600)' }}
          />
          {!visualDocked && (
            certCertified ? (
              <span className="text-xs font-semibold text-yellow-400 title-shimmer">
                {certTitle}
              </span>
            ) : certStarted ? (
              <>
                <span className="text-xs font-semibold text-[#111]">{certConfig.label}</span>
                <span className="text-xs text-[#59616b]">{certXp} XP</span>
              </>
            ) : (
              <span className="text-xs font-semibold text-[#444]">Get Certified</span>
            )
          )}
        </button>
      </div>
    </aside>
  )
}
