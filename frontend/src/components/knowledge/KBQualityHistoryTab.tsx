import { useCallback } from 'react'
import { getKBQuality } from '../../api/knowledge'
import { QualityTimeline } from '../shared/QualityTimeline'

interface Props {
  kbUuid: string
  onSwitchToAutovalidate?: () => void
}

/** Thin adapter over the shared QualityTimeline (Phase 4). */
export function KBQualityHistoryTab({ kbUuid, onSwitchToAutovalidate }: Props) {
  const fetchHistory = useCallback(() => getKBQuality(kbUuid), [kbUuid])
  return (
    <QualityTimeline
      fetchHistory={fetchHistory}
      itemKindLabel="KB"
      itemKindPluralLabel="KBs"
      sampleNoun="queries"
      onSwitchToAutovalidate={onSwitchToAutovalidate}
    />
  )
}
