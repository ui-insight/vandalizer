import { useCallback } from 'react'
import { downloadKBValidationRunExport, getKBQuality, type KBValidationResult } from '../../api/knowledge'
import { QualityTimeline, type QualityHistoryItem, type QualityRunExportFormat } from '../shared/QualityTimeline'

interface Props {
  onOpenRun?: (uuid: string, result: KBValidationResult, createdAt?: string) => void
  kbUuid: string
  onSwitchToAutovalidate?: () => void
  /** Bumped by the panel when a validation run finishes, to refetch history. */
  refreshKey?: number
  /** True while a validation run is in flight, to poll for the landing row. */
  polling?: boolean
  /** False for a KB with no sources: it can't be validated, so an empty history
   *  is a plain statement of fact rather than a prompt to go run one. */
  kbHasSources?: boolean
}

/** Thin adapter over the shared QualityTimeline (Phase 4). */
export function KBQualityHistoryTab({ onOpenRun, kbUuid, onSwitchToAutovalidate, refreshKey, polling, kbHasSources = true }: Props) {
  const fetchHistory = useCallback(() => getKBQuality(kbUuid), [kbUuid])
  const exportRun = useCallback(
    (runUuid: string, format: QualityRunExportFormat) =>
      downloadKBValidationRunExport(kbUuid, runUuid, format),
    [kbUuid],
  )
  return (
    <QualityTimeline
      fetchHistory={fetchHistory}
      itemKindLabel="KB"
      itemKindPluralLabel="KBs"
      sampleNoun="queries"
      onSwitchToAutovalidate={onSwitchToAutovalidate}
      refreshKey={refreshKey}
      polling={polling}
      onExportRun={exportRun}
      canOpenRun={hasSavedResult}
      onOpenRun={onOpenRun ? item => {
        if (hasSavedResult(item)) onOpenRun(item.uuid!, item.result_snapshot as KBValidationResult, item.created_at)
      } : undefined}
      blockedReason={kbHasSources
        ? null
        : 'Add at least one source, then run Validate & improve to record a quality score here.'}
    />
  )
}

// Legacy and optimizer-apply rows may have no per-question snapshot.
function hasSavedResult(item: QualityHistoryItem): boolean {
  const snapshot = item.result_snapshot as Partial<KBValidationResult> | null | undefined
  return !!item.uuid && item.source !== 'optimizer_apply' && Array.isArray(snapshot?.retrieval_precision?.details)
}
