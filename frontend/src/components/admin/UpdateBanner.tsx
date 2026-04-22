import { useEffect, useState } from 'react'
import { ArrowUpCircle, ExternalLink, X } from 'lucide-react'
import { getVersionStatus, type VersionStatus } from '../../api/admin'

const DISMISS_KEY_PREFIX = 'vandalizer:update-banner-dismissed:'

export function UpdateBanner() {
  const [status, setStatus] = useState<VersionStatus | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let cancelled = false
    getVersionStatus()
      .then((s) => { if (!cancelled) setStatus(s) })
      .catch(() => { /* silent — banner is an optional signal */ })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!status?.latest) return
    const key = `${DISMISS_KEY_PREFIX}${status.latest}`
    setDismissed(localStorage.getItem(key) === '1')
  }, [status?.latest])

  if (!status || !status.update_available || !status.latest || dismissed) {
    return null
  }

  const dismiss = () => {
    if (status.latest) {
      localStorage.setItem(`${DISMISS_KEY_PREFIX}${status.latest}`, '1')
    }
    setDismissed(true)
  }

  return (
    <div className="mb-4 flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-900">
      <ArrowUpCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
      <div className="flex-1 text-sm">
        <div className="font-medium">
          Update available: {status.latest}
        </div>
        <div className="text-amber-800">
          You are running {status.current}. See the release notes, then run{' '}
          <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-xs">
            ./upgrade.sh {status.latest}
          </code>{' '}
          on the host to upgrade.
        </div>
        {status.release_url && (
          <a
            href={status.release_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-sm font-medium underline hover:no-underline"
          >
            View release notes
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
      <button
        onClick={dismiss}
        aria-label="Dismiss update notice"
        className="rounded p-1 text-amber-700 hover:bg-amber-100 hover:text-amber-900"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
