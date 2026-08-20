import { useCallback } from 'react'
import { downloadKBValidationRunExport, getKBQuality } from '../../api/knowledge'
import { QualityTimeline, type QualityRunExportFormat } from '../shared/QualityTimeline'

interface Props {
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
export function KBQualityHistoryTab({ kbUuid, onSwitchToAutovalidate, refreshKey, polling, kbHasSources = true }: Props) {
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
      blockedReason={kbHasSources
        ? null
        : 'Add at least one source, then run Validate & improve to record a quality score here.'}
    />
  )
}
