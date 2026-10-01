import { useEffect, useRef, useState } from 'react'
import {
  PackageOpen, CheckCircle2, AlertTriangle, Loader2, ArrowUpCircle, Trash2,
} from 'lucide-react'
import {
  getCatalogPreview, getCatalogStatus, applyCatalogUpgrade,
  type CatalogJob,
} from '../../api/admin'

import { useAdminQuery } from './shared/useAdminQuery'

function VersionPill({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs uppercase tracking-wide text-gray-500">{label}</span>
      <span className={`font-mono text-lg ${accent ? 'text-amber-700 font-semibold' : 'text-gray-900'}`}>
        {value}
      </span>
    </div>
  )
}

export function CatalogTab() {
  const { data: preview, loading, error: previewError, load: loadPreview } = useAdminQuery(getCatalogPreview)
  const [job, setJob] = useState<CatalogJob | null>(null)
  const [prune, setPrune] = useState(true)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [pollAttempt, setPollAttempt] = useState(0)
  const pending = useRef(false)
  const mounted = useRef(false)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => { if (preview) setJob(preview.job) }, [preview])

  // Only one status request is in flight. A failed read never starts another upgrade.
  useEffect(() => {
    if (job?.state !== 'running') return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const status = await getCatalogStatus()
        if (cancelled) return
        if (!status.job) throw new Error('The accepted upgrade has no recorded status yet. Retry its status before starting another upgrade.')
        setStatusError(null)
        setJob(status.job)
        if (status.job.state === 'running') timer = setTimeout(poll, 3000)
        else loadPreview()
      } catch (reason) {
        if (!cancelled) setStatusError(reason instanceof Error ? reason.message : 'Unable to refresh upgrade status.')
      }
    }
    timer = setTimeout(poll, 1000)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [job?.state, pollAttempt, loadPreview])

  const apply = async () => {
    if (pending.current || job?.state === 'running') return
    pending.current = true
    setError(null)
    setStatusError(null)
    setApplying(true)
    try {
      const accepted = await applyCatalogUpgrade(prune)
      if (mounted.current) setJob({ state: 'running', target_version: accepted.target_version, prune: accepted.prune })
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : 'Failed to start upgrade')
    } finally {
      pending.current = false
      if (mounted.current) setApplying(false)
    }
  }

  if (loading) {
    return <div className="flex items-center gap-2 p-6 text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading catalog status…</div>
  }
  if (!preview) {
    return <div role="alert" className="p-6 text-red-800">{previewError || 'Catalog status unavailable.'} <button onClick={loadPreview} className="underline">Retry catalog preview</button></div>
  }

  const running = job?.state === 'running' || applying
  const { counts } = preview

  return (
    <div className="max-w-3xl space-y-6 p-1">
      <div className="flex items-center gap-2">
        <PackageOpen className="h-5 w-5 text-gray-700" />
        <h2 className="text-lg font-semibold text-gray-900">Starter examples</h2>
      </div>

      {/* Version summary */}
      <div className="flex flex-wrap items-center gap-6 rounded-lg border border-gray-200 bg-white p-4">
        <VersionPill label="Applied" value={preview.applied_version || 'none'} />
        <ArrowUpCircle className="h-5 w-5 text-gray-400" />
        <VersionPill label="Bundled (available)" value={preview.bundled_version} accent={preview.update_available} />
      </div>

      {statusError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Status refresh failed: {statusError} The accepted upgrade may still be running. <button onClick={() => { setStatusError(null); setPollAttempt(value => value + 1) }} className="underline">Retry upgrade status</button></div>}
      {error && (
        <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" /> {error}
        </div>
      )}

      {/* Completed / failed banners */}
      {job?.state === 'completed' && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{job.message || 'Catalog upgrade completed.'}</span>
        </div>
      )}
      {job?.state === 'failed' && (
        <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{job.message || 'Catalog upgrade failed.'}</span>
        </div>
      )}

      {running ? (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <Loader2 className="h-4 w-4 animate-spin" />
          {statusError ? 'Last known status: applying' : 'Applying'} catalog {job?.target_version || preview.bundled_version}… You can leave this page; you'll get a notification when it finishes.
        </div>
      ) : !preview.update_available ? (
        <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600">
          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          Catalog is up to date ({preview.bundled_version}).
        </div>
      ) : (
        <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-4">
          <div className="text-sm font-medium text-gray-900">
            Applying {preview.bundled_version} will:
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            <span className="text-emerald-700">+ {counts.new} new</span>
            <span className="text-gray-600">~ {counts.refreshed} refreshed</span>
            <span className="text-red-600">- {counts.retiring} retiring</span>
          </div>

          {/* New items */}
          {preview.new.length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-emerald-700">{preview.new.length} new item(s)</summary>
              <ul className="mt-2 space-y-1 pl-4 text-gray-600">
                {preview.new.map((it) => (
                  <li key={`${it.type}:${it.seed_id}`}>[{it.label}] {it.name}</li>
                ))}
              </ul>
            </details>
          )}

          {/* Retirement toggle + list */}
          {counts.retiring > 0 && (
            <div className="rounded-md border border-red-100 bg-red-50/50 p-3">
              <label className="flex items-center gap-2 text-sm font-medium text-gray-800">
                <input
                  type="checkbox"
                  checked={prune}
                  onChange={(e) => setPrune(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300"
                />
                <Trash2 className="h-4 w-4 text-red-500" />
                Also retire {counts.retiring} dropped item(s)
              </label>
              <p className="mt-1 pl-6 text-xs text-gray-500">
                Soft-archive: removed from Explore, underlying records kept (reversible). Uncheck to upgrade without removing them.
              </p>
              <ul className="mt-2 space-y-1 pl-6 text-sm text-gray-600">
                {preview.retiring.map((it) => (
                  <li key={`${it.type}:${it.seed_id}:${it.id}`}>[{it.label}] {it.name}</li>
                ))}
              </ul>
            </div>
          )}

          <button
            onClick={apply}
            disabled={applying}
            className="inline-flex items-center gap-2 rounded-lg bg-amber-700 px-4 py-2 text-sm font-medium text-white hover:bg-amber-800 disabled:opacity-50"
          >
            <ArrowUpCircle className="h-4 w-4" />
            Apply catalog {preview.bundled_version}
          </button>
        </div>
      )}
    </div>
  )
}
