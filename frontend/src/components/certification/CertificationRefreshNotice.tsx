import { useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'

/** A refresh retries only the progress read, never the successful learner action. */
export function CertificationRefreshNotice() {
  const cert = useCertificationPanelOptional()
  if (!cert?.refreshError) return null
  return (
    <div className="m-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
      <p role="status">{cert.savedWritePendingRefresh
        ? 'Your certification action was saved, but the progress display is awaiting refresh. You do not need to submit it again.'
        : 'Certification progress could not be loaded. Retry to see your saved work.'}</p>
      <button type="button" className="mt-2 rounded-md border border-amber-800 bg-white px-3 py-2 font-medium focus-visible:outline-2 focus-visible:outline-offset-2" disabled={cert.loading} onClick={() => void cert.refresh()}>
        {cert.loading ? 'Refreshing certification progress…' : 'Refresh certification progress'}
      </button>
    </div>
  )
}
