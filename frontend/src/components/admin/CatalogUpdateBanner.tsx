import { useEffect, useState } from 'react'
import { PackageOpen, X } from 'lucide-react'
import { getCatalogStatus, type CatalogStatus } from '../../api/admin'

const DISMISS_KEY_PREFIX = 'vandalizer:catalog-banner-dismissed:'

/**
 * Amber banner shown on the Admin page when the bundled verified catalog is
 * newer than what's applied. Mirrors UpdateBanner, but the action is in-app:
 * it points the admin at the Catalog tab to preview and apply.
 */
export function CatalogUpdateBanner({ onView }: { onView?: () => void }) {
  const [status, setStatus] = useState<CatalogStatus | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let cancelled = false
    getCatalogStatus()
      .then((s) => { if (!cancelled) setStatus(s) })
      .catch(() => { /* silent — banner is an optional signal */ })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!status?.bundled_version) return
    const key = `${DISMISS_KEY_PREFIX}${status.bundled_version}`
    setDismissed(localStorage.getItem(key) === '1')
  }, [status?.bundled_version])

  const running = status?.job?.state === 'running'
  if (!status || !status.update_available || dismissed || running) {
    return null
  }

  const dismiss = () => {
    localStorage.setItem(`${DISMISS_KEY_PREFIX}${status.bundled_version}`, '1')
    setDismissed(true)
  }

  return (
    <div className="mb-4 flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-900">
      <PackageOpen className="mt-0.5 h-5 w-5 flex-shrink-0" />
      <div className="flex-1 text-sm">
        <div className="font-medium">
          Catalog update available: {status.bundled_version}
        </div>
        <div className="text-amber-800">
          Your verified catalog is at {status.applied_version || 'none'}. Review what changes
          (including any items that will be retired) and apply it from the Catalog tab.
        </div>
        {onView && (
          <button
            onClick={onView}
            className="mt-1 inline-flex items-center gap-1 text-sm font-medium underline hover:no-underline"
          >
            Review &amp; apply
          </button>
        )}
      </div>
      <button
        onClick={dismiss}
        aria-label="Dismiss catalog update notice"
        className="rounded p-1 text-amber-700 hover:bg-amber-100 hover:text-amber-900"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
