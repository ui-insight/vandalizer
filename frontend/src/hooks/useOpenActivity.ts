import { useCallback } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { getActivity } from '../api/activity'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { useToast } from '../contexts/ToastContext'
import type { ActivityEvent } from '../types/chat'
import type { CrossFieldRunReport, DocumentWarning, ExtractionSourceMap } from '../api/extractions'

// A workflow run parked on an approval gate carries the pending review's uuid
// in meta_summary. The status stays "running" (ActivityStatus has no paused
// member), so this marker is what separates "waiting on a person" from
// "waiting on a worker" everywhere in the rail.
export function pendingReviewUuid(activity: ActivityEvent): string | null {
  const uuid = (activity.meta_summary as { pending_review_uuid?: unknown } | undefined)
    ?.pending_review_uuid
  return typeof uuid === 'string' && uuid ? uuid : null
}

/** Reopen an activity where it lives: the conversation in the assistant tab,
 * the workflow run in its editor (or its pending review), the extraction run
 * with its snapshot restored.
 *
 * Resuming is navigation, not a prompt — the chat agent has no tool that
 * reopens a past conversation, so "continue where you left off" surfaces must
 * come through here rather than send the agent a message about it.
 */
export function useOpenActivity() {
  const { setActiveRightTab, setLoadConversationId, openWorkflow, openExtraction, closeWorkflow, closeExtraction, closeAutomation } = useWorkspace()
  const navigate = useNavigate()
  const { toast } = useToast()

  const openActivity = useCallback(
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
        const snapSources = activity.result_snapshot?.sources as ExtractionSourceMap | undefined
        const initialSources = snapSources && typeof snapSources === 'object' && Object.keys(snapSources).length > 0
          ? snapSources
          : undefined
        // The run's cross-field verdict is in the same snapshot. Restoring
        // values without it re-opens a run that failed a budget rule looking
        // exactly like one that passed.
        const snap = activity.result_snapshot as {
          cross_field?: CrossFieldRunReport | null
          cross_field_sets?: (CrossFieldRunReport | null)[]
          document_warnings?: DocumentWarning[]
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

  /** Open by id, for surfaces that only carry the activity's id (the home). */
  const openActivityById = useCallback(
    async (activityId: string) => {
      try {
        const { activity } = await getActivity(activityId)
        openActivity(activity)
      } catch (err) {
        toast(err instanceof Error ? err.message : 'Could not open that activity', 'error')
      }
    },
    [openActivity, toast],
  )

  return { openActivity, openActivityById }
}
