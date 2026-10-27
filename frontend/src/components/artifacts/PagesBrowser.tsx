import { useEffect, useRef, useState } from 'react'
import { browseArtifacts, createArtifact, type ArtifactPageResult } from '../../api/artifacts'
import { addProjectPin } from '../../api/projects'

const button = 'rounded border border-gray-300 bg-white px-3 py-2 text-sm disabled:opacity-50'
const message = (e: unknown) => e instanceof Error ? e.message : 'Could not load pages. Please try again.'

export function PagesBrowser({ projectUuid, canManage = false }: { projectUuid?: string; canManage?: boolean }) {
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('updated')
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const [result, setResult] = useState<ArtifactPageResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const request = useRef(crypto.randomUUID())
  const pending = useRef(false)
  useEffect(() => { const timer = setTimeout(() => { setQuery(search.trim()); setPage(1) }, 250); return () => clearTimeout(timer) }, [search])
  useEffect(() => {
    let live = true
    setLoading(true); setError(''); setResult(null)
    browseArtifacts({ search: query, sort, page, project_uuid: adding ? undefined : projectUuid })
      .then(data => { if (live) setResult(data) })
      .catch(e => { if (live) setError(message(e)) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [query, sort, page, adding, projectUuid, refresh])
  const act = async (work: () => Promise<void>) => {
    if (pending.current) return
    pending.current = true; setBusy(true); setError('')
    try { await work() } catch (e) { setError(message(e)) }
    finally { pending.current = false; setBusy(false) }
  }
  return <section aria-label={projectUuid ? 'Project pages' : 'Saved pages'} className="min-w-0 space-y-4 p-4 text-gray-900">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-xl font-semibold">{adding ? 'Add an existing page' : projectUuid ? 'Project pages' : 'Pages'}</h2>
      <button className={button} disabled={busy} onClick={() => void act(async () => {
        const saved = await createArtifact('Untitled page', '<main><h1>Your page</h1><p>Edit this page to get started.</p></main>', request.current, projectUuid)
        window.location.assign(`/artifacts/${saved.uuid}`)
      })}>New page</button>
      {projectUuid && canManage && <button className={button} disabled={busy} onClick={() => { setAdding(!adding); setSearch(''); setQuery(''); setPage(1) }}>{adding ? 'Back to project pages' : 'Add existing page'}</button>}
    </div>
    <p className="text-sm text-gray-600">Saved HTML pages from chat and workflows. New pages are private. {projectUuid && 'Only pages you can access appear here; adding a page does not change its sharing settings.'}</p>
    <div className="flex flex-wrap gap-3">
      <label className="min-w-0 flex-1 text-sm">Search pages<input className="mt-1 w-full rounded border p-2" type="search" value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label className="text-sm">Sort pages<select className="mt-1 block rounded border p-2" value={sort} onChange={e => { setSort(e.target.value); setPage(1) }}><option value="updated">Recently updated</option><option value="newest">Newest first</option><option value="title">Title</option></select></label>
    </div>
    {error && <p role="alert" className="text-sm text-red-800">{error} <button className="underline" onClick={() => setRefresh(n => n + 1)}>Retry pages</button></p>}
    {loading ? <p role="status">Loading pages…</p> : result && <>
      {!result.items.length && <p>{query ? 'No pages match your search.' : 'No pages yet. Save a chat or workflow output, or create a page.'}</p>}
      <ul className="grid gap-3">{result.items.map(item => <li key={item.uuid} className="min-w-0 rounded-lg border p-3">
        <a className="break-words font-semibold underline" href={`/artifacts/${encodeURIComponent(item.uuid)}`}>{item.title}</a>
        <p className="mt-1 text-sm text-gray-600">{item.published_revision ? 'Public revision available' : item.team_id ? 'Team access' : 'Private'} · {item.revisions.length} revision{item.revisions.length === 1 ? '' : 's'}</p>
        {item.updated_at && <p className="text-xs text-gray-500">Updated {new Date(item.updated_at).toLocaleString()}</p>}
        {adding && projectUuid && <button className={`${button} mt-2`} disabled={busy} onClick={() => void act(async () => { await addProjectPin(projectUuid, { pin_type: 'artifact', target_id: item.uuid }); setAdding(false); setPage(1); setSearch(''); setQuery(''); setRefresh(n => n + 1) })}>Add {item.title} to project</button>}
      </li>)}</ul>
      <nav aria-label="Pages pagination" className="flex flex-wrap items-center gap-3 text-sm">
        <button className={button} disabled={page === 1} onClick={() => setPage(n => n - 1)}>Previous</button>
        <span>Page {page} of {Math.max(1, Math.ceil(result.total / result.page_size))} · {result.total} pages</span>
        <button className={button} disabled={page * result.page_size >= result.total} onClick={() => setPage(n => n + 1)}>Next</button>
      </nav>
    </>}
  </section>
}
