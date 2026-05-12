import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'
import { getTimeSaved, type TimeSavedSummary } from '../../api/auth'

/**
 * Small workspace-nav badge showing the user's cumulative estimated
 * time-saved across extractions, workflow runs, and chat queries.
 *
 * Hidden until the user has accrued at least 1 minute — avoids a "0m saved"
 * badge that adds nothing on day 0.
 *
 * Calibration lives server-side in app/services/time_saved.py.
 */
export function TimeSavedBadge() {
  const [summary, setSummary] = useState<TimeSavedSummary | null>(null)

  useEffect(() => {
    let cancelled = false
    getTimeSaved()
      .then(s => {
        if (!cancelled) setSummary(s)
      })
      .catch(() => {
        // Silent: badge is decorative; failure shouldn't disrupt the nav.
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (!summary || summary.total_minutes < 1) return null

  return (
    <div
      className="flex items-center gap-1.5 rounded-[30px] border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-[#555]"
      title="Estimated time saved from extractions, workflows, and chat queries. Conservative per-event estimates; see system docs for methodology."
      aria-label={`${summary.total_label} of estimated time saved`}
    >
      <Clock className="h-3.5 w-3.5" />
      <span>{summary.total_label} saved</span>
    </div>
  )
}
