import { useCallback } from 'react'
import { getWorkflowQuality } from '../../api/workflows'
import { QualityTimeline } from '../shared/QualityTimeline'

interface Props {
  workflowId: string
  onSwitchToAutovalidate?: () => void
}

/** Workflow quality history — Phase 3+4 of the loop-closure plan.
 *  Backed by the unified ``/api/workflows/{id}/quality`` endpoint and
 *  rendered by the shared QualityTimeline component so all three optimizer
 *  surfaces (KB, extraction, workflow) share one visualisation. */
export function WorkflowQualityHistoryTab({ workflowId, onSwitchToAutovalidate }: Props) {
  const fetchHistory = useCallback(() => getWorkflowQuality(workflowId), [workflowId])
  return (
    <QualityTimeline
      fetchHistory={fetchHistory}
      itemKindLabel="workflow"
      itemKindPluralLabel="workflows"
      sampleNoun="checks"
      onSwitchToAutovalidate={onSwitchToAutovalidate}
    />
  )
}
