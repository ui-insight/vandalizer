import { useEffect, useState } from 'react'
import { getQualitySparkline } from '../api/extractions'

interface SparklinePoint {
  score: number
  created_at: string
}

export function useQualitySparkline(kind: 'search_set' | 'workflow', itemId: string | undefined) {
  const [scores, setScores] = useState<SparklinePoint[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!itemId) return

    setLoading(true)
    if (kind === 'search_set') {
      getQualitySparkline(itemId)
        .then(r => setScores(r.scores))
        .catch(() => {})
        .finally(() => setLoading(false))
    } else {
      // Workflow sparklines use the workflows API
      import('../api/client').then(({ apiFetch }) => {
        apiFetch<{ scores: SparklinePoint[] }>(`/api/workflows/${itemId}/quality-sparkline?limit=10`)
          .then(r => setScores(r.scores))
          .catch(() => {})
          .finally(() => setLoading(false))
      })
    }
  }, [kind, itemId])

  return { scores, loading }
}
